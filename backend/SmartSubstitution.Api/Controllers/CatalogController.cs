using Microsoft.AspNetCore.Mvc;
using SmartSubstitution.Api.Services;

namespace SmartSubstitution.Api.Controllers;

[ApiController]
[Route("[controller]")]
public class CatalogController : ControllerBase
{
    private readonly LocalCatalogService _catalog;

    public CatalogController(LocalCatalogService catalog) => _catalog = catalog;

    /// <summary>GET /catalog/diagnostic - connection check + document count</summary>
    [HttpGet("diagnostic")]
    public async Task<IActionResult> Diagnostic(CancellationToken ct) =>
        Ok(await _catalog.DiagnosticAsync(ct));

    /// <summary>
    /// GET /catalog/search?q=appelsin&amp;contracts=3439,3440&amp;limit=20
    /// Text search scoped to the supplied contract numbers.
    /// </summary>
    [HttpGet("search")]
    public async Task<IActionResult> Search(
        [FromQuery] string q,
        [FromQuery] string? contracts = null,
        [FromQuery] int limit = 20,
        CancellationToken ct = default)
    {
        if (string.IsNullOrWhiteSpace(q))
            return BadRequest(new { error = "Query parameter 'q' is required" });

        var contractList = ParseContracts(contracts);
        var results = await _catalog.SearchAsync(q, contractList, limit, ct);
        return Ok(results);
    }

    /// <summary>GET /catalog/{itemNumber}?contracts=3439,3440</summary>
    [HttpGet("{itemNumber}")]
    public async Task<IActionResult> GetByItemNumber(
        string itemNumber,
        [FromQuery] string? contracts = null,
        CancellationToken ct = default)
    {
        var contractList = ParseContracts(contracts);
        var product = await _catalog.GetByItemNumberAsync(itemNumber, contractList, ct);
        return product is null ? NotFound() : Ok(product);
    }

    /// <summary>
    /// GET /catalog/{itemNumber}/candidates?contracts=3439,3440
    /// Replacement candidates in the same category, scoped to the supplied contract numbers.
    /// Availability is read directly from the product's StockAreas field.
    /// </summary>
    [HttpGet("{itemNumber}/candidates")]
    public async Task<IActionResult> GetCandidates(
        string itemNumber,
        [FromQuery] string contracts,
        CancellationToken ct = default)
    {
        var contractList = ParseContracts(contracts);
        if (contractList is not { Count: > 0 })
            return BadRequest(new { error = "Query parameter 'contracts' must contain at least one contract number" });

        var product = await _catalog.GetByItemNumberAsync(itemNumber, contractList, ct);
        if (product is null)
            return NotFound(new { error = $"Product '{itemNumber}' not found in the supplied contracts" });

        var candidates = await _catalog.GetCandidatesAsync(product, contractList, ct: ct);

        return Ok(new
        {
            requestedProduct = LocalCatalogService.ToRequestedProduct(product),
            contractNumbers  = contractList,
            candidateCount   = candidates.Count,
            candidates       = candidates.Select(c => LocalCatalogService.ToCandidate(c)).ToList(),
        });
    }

    private static List<string>? ParseContracts(string? contracts) =>
        string.IsNullOrWhiteSpace(contracts)
            ? null
            : contracts.Split(',', StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries).ToList();
}
