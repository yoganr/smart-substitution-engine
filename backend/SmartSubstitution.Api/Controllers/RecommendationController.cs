using System.Diagnostics;
using Microsoft.AspNetCore.Mvc;
using MongoDB.Driver;
using SmartSubstitution.Api.Dtos;
using SmartSubstitution.Api.Models;
using SmartSubstitution.Api.Services;

namespace SmartSubstitution.Api.Controllers;

[ApiController]
[Route("[controller]")]
public class RecommendationController : ControllerBase
{
    private readonly IMongoDatabase _db;
    private readonly CandidateProductService _candidates;
    private readonly PythonAiClient _pythonAi;

    public RecommendationController(
        IMongoDatabase db,
        CandidateProductService candidates,
        PythonAiClient pythonAi)
    {
        _db = db;
        _candidates = candidates;
        _pythonAi = pythonAi;
    }

    /// <summary>
    /// POST /recommendation/replacements
    /// Checks inventory, queries candidates, calls Python AI, logs result.
    /// </summary>
    [HttpPost("replacements")]
    public async Task<ActionResult<ReplacementResponseDto>> GetReplacements(
        [FromBody] ReplacementRequestDto request,
        CancellationToken ct)
    {
        var products = _db.GetCollection<Product>("products");
        var inventory = _db.GetCollection<Inventory>("inventory");
        var contracts = _db.GetCollection<Contract>("contracts");
        var logs = _db.GetCollection<RecommendationLog>("recommendation_logs");
        var companies = _db.GetCollection<Company>("companies");

        // 1. Load company
        var company = await companies
            .Find(c => c.CompanyId == request.CompanyId)
            .FirstOrDefaultAsync(ct);
        if (company is null)
            return NotFound(new { error = $"Company '{request.CompanyId}' not found" });

        // 2. Load requested product
        var product = await products
            .Find(p => p.ProductId == request.ProductId)
            .FirstOrDefaultAsync(ct);
        if (product is null)
            return NotFound(new { error = $"Product '{request.ProductId}' not found" });

        // 3. Check inventory
        var inv = await inventory
            .Find(i => i.ProductId == request.ProductId)
            .FirstOrDefaultAsync(ct);

        if (inv is not null && inv.StockQuantity >= request.RequestedQuantity)
            return Ok(new ReplacementResponseDto(ReplacementNeeded: false));

        // 4. Load company contracts
        var contract = await contracts
            .Find(c => c.CompanyId == request.CompanyId)
            .FirstOrDefaultAsync(ct);
        var contractItems = contract?.Items ?? new();

        // 5. Query candidate products
        var candidatesWithStock = await _candidates.GetCandidatesAsync(
            product.CategoryId, product.ProductId, contractItems, ct);

        // 6. Build Python request payload
        var pythonRequest = new PythonReplacementRequestDto(
            Company: new PythonCompanyDto(company.CompanyId, company.Name),
            RequestedProduct: new PythonProductDto(
                product.ProductId, product.Name, product.CategoryId,
                product.Brand, product.Unit, product.PackSize, product.BasePrice,
                product.DietaryTags),
            RequestedQuantity: request.RequestedQuantity,
            ContractItems: contractItems
                .Select(ci => new PythonContractItemDto(ci.ProductId, ci.ContractPrice, ci.IsPreferred))
                .ToList(),
            CandidateProducts: candidatesWithStock.Select(c =>
                new PythonCandidateProductDto(
                    c.Product.ProductId, c.Product.Name, c.Product.CategoryId,
                    c.Product.Brand, c.Product.Unit, c.Product.PackSize,
                    c.Product.BasePrice, c.StockQuantity,
                    c.ContractPrice, c.Product.IsActive, c.Product.DietaryTags))
                .ToList(),
            MaxResults: request.MaxResults,
            UseAiExplanation: request.UseAiExplanation);

        // 7. Call Python AI service
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

        // 8. Log to Atlas
        var log = new RecommendationLog
        {
            CompanyId = request.CompanyId,
            RequestedProductId = request.ProductId,
            ReplacementCount = pythonResponse?.Replacements?.Count ?? 0,
            TopProductId = pythonResponse?.Replacements?.FirstOrDefault()?.ProductId,
            TopScore = pythonResponse?.Replacements?.FirstOrDefault()?.FinalScore ?? 0,
            PythonResponseMs = sw.ElapsedMilliseconds,
        };
        await logs.InsertOneAsync(log, cancellationToken: ct);

        // 9. Map and return
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
        var logs = _db.GetCollection<RecommendationLog>("recommendation_logs");
        var result = await logs.Find(_ => true).Limit(100).ToListAsync(ct);
        return Ok(result);
    }
}
