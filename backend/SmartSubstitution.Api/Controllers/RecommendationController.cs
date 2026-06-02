using System.Diagnostics;
using Microsoft.AspNetCore.Mvc;
using MongoDB.Driver;
using SmartSubstitution.Api.Dtos;
using SmartSubstitution.Api.Models;
using SmartSubstitution.Api.Services;

namespace SmartSubstitution.Api.Controllers;

[ApiController]
[Route("recommendations")]
public class RecommendationController : ControllerBase
{
    private readonly IMongoDatabase      _db;
    private readonly LocalCatalogService _catalog;
    private readonly PythonAiClient      _pythonAi;

    public RecommendationController(
        IMongoDatabase db,
        LocalCatalogService catalog,
        PythonAiClient pythonAi)
    {
        _db       = db;
        _catalog  = catalog;
        _pythonAi = pythonAi;
    }

    /// <summary>
    /// POST /recommendations/replacements
    ///
    /// Finds replacement candidates for an out-of-stock product, restricted
    /// to the contract numbers (catalogs) the requesting user has access to.
    /// All candidates ARE contract products, so they all receive the
    /// contract-match scoring bonus in the Python AI service.
    /// </summary>
    [HttpPost("replacements")]
    public async Task<ActionResult<ReplacementResponseDto>> GetReplacements(
        [FromBody] ReplacementRequestDto request,
        CancellationToken ct)
    {
        if (request.Product is null)
            return BadRequest(new { error = "product (itemNumber, sellerAccountNumber, contractNumber) is required" });
        if (request.ContractNumbers is not { Count: > 0 })
            return BadRequest(new { error = "contractNumbers must contain at least one value" });

        var p = request.Product;
        var preferredPartType = request.PreferredPartType?.ToUpperInvariant() switch
        {
            "CU" => "CU",
            "TU" => "TU",
            _    => null,
        };

        // 1. Exact product lookup via composite key
        var product = await _catalog.GetByCompositeKeyAsync(p.ItemNumber, p.SellerAccountNumber, p.ContractNumber, ct);
        if (product is null)
            return NotFound(new { error = $"Product '{p.ItemNumber}' not found for seller '{p.SellerAccountNumber}' / contract '{p.ContractNumber}'" });

        // 2. Check availability for the preferred PartType specifically.
        //    e.g. Coca-Cola only in TU but user wants CU → not available → find replacements.
        //    No StockAreas = stock unknown → proceed to find replacements.
        var available = preferredPartType switch
        {
            "CU" => product.IsCuAvailable,
            "TU" => product.IsTuAvailable,
            _    => product.IsAvailable,
        };
        if (available)
            return Ok(new ReplacementResponseDto(ReplacementNeeded: false));

        // 3. Find candidates: same category, user's contract numbers, preferred PartType
        var candidates = await _catalog.GetCandidatesAsync(product, request.ContractNumbers, preferredPartType, ct);

        // 4. Build Python AI request.
        //    Every candidate is a contracted product, so we pass it as both a
        //    candidateProduct and a contractItem - this ensures the Python scorer
        //    awards the full contract-match bonus to every result.
        var contractItems = candidates
            .Select(c => new PythonContractItemDto(
                ProductId:     c.ItemNumber,
                ContractPrice: (double)(c.ConsumerUnit?.Price.UnitPriceDecimal
                                        ?? c.TradeUnit?.Price.UnitPriceDecimal ?? 0m),
                IsPreferred:   c.PreferredProduct))
            .ToList();

        var pythonRequest = new PythonReplacementRequestDto(
            Company:           new PythonCompanyDto(
                                   Id:   request.ContractNumbers.First(),
                                   Name: string.Join(", ", request.ContractNumbers)),
            RequestedProduct:  LocalCatalogService.ToRequestedProduct(product, preferredPartType),
            RequestedQuantity: request.RequestedQuantity,
            ContractItems:     contractItems,
            CandidateProducts: candidates.Select(c => LocalCatalogService.ToCandidate(c, preferredPartType)).ToList(),
            MaxResults:        request.MaxResults,
            UseAiExplanation:  request.UseAiExplanation);

        // 5. Call Python AI service
        var sw = Stopwatch.StartNew();
        PythonReplacementResponseDto? pythonResponse;
        try
        {
            pythonResponse = await _pythonAi.GetReplacementsAsync(pythonRequest, ct);
        }
        catch (Exception ex)
        {
            return StatusCode(503, new { error = "AI recommendation service unavailable", detail = ex.Message });
        }
        sw.Stop();

        // 6. Log to Atlas
        var log = new RecommendationLog
        {
            ItemNumber         = p.ItemNumber,
            SellerAccountNumber= p.SellerAccountNumber,
            ContractNumber     = p.ContractNumber,
            ContractNumbers    = request.ContractNumbers,
            ReplacementCount   = pythonResponse?.Replacements?.Count ?? 0,
            TopProductId       = pythonResponse?.Replacements?.FirstOrDefault()?.ProductId,
            TopScore           = pythonResponse?.Replacements?.FirstOrDefault()?.FinalScore ?? 0,
            PythonResponseMs   = sw.ElapsedMilliseconds,
        };
        var logs = _db.GetCollection<RecommendationLog>("recommendation_logs");
        await logs.InsertOneAsync(log, cancellationToken: ct);

        // 7. Map and return
        if (pythonResponse is null)
            return StatusCode(502, new { error = "Empty response from AI service" });

        return Ok(new ReplacementResponseDto(
            ReplacementNeeded: true,
            Replacements: pythonResponse.Replacements?
                .Select(r => new ReplacementDto(
                    r.ProductId, r.Name, r.FinalScore, r.ConfidencePct, r.ConfidenceLabel,
                    new ScoreBreakdownDto(
                        r.ScoreBreakdown.CategorySimilarity,
                        r.ScoreBreakdown.ContractMatch,
                        r.ScoreBreakdown.PriceSimilarity,
                        r.ScoreBreakdown.StockAvailability,
                        r.ScoreBreakdown.UnitPackSimilarity),
                    r.Explanation))
                .ToList(),
            RejectedCandidates: pythonResponse.RejectedCandidates?
                .Select(rc => new RejectedCandidateDto(rc.ProductId, rc.Name, rc.RejectionReason))
                .ToList(),
            NoCandidatesReason: pythonResponse.NoCandidatesReason));
    }

    [HttpGet("logs")]
    public async Task<IActionResult> GetLogs(CancellationToken ct)
    {
        var logs   = _db.GetCollection<RecommendationLog>("recommendation_logs");
        var result = await logs.Find(_ => true).SortByDescending(l => l.CreatedAt).Limit(100).ToListAsync(ct);
        return Ok(result);
    }
}
