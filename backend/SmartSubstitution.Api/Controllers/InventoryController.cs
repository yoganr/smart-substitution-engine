using Microsoft.AspNetCore.Mvc;
using MongoDB.Driver;
using SmartSubstitution.Api.Dtos;
using SmartSubstitution.Api.Models;

namespace SmartSubstitution.Api.Controllers;

[ApiController]
[Route("[controller]")]
public class InventoryController : ControllerBase
{
    private readonly IMongoCollection<Inventory> _inventory;

    public InventoryController(IMongoDatabase db)
        => _inventory = db.GetCollection<Inventory>("inventory");

    [HttpGet("{productId}")]
    public async Task<IActionResult> GetByProductId(string productId, CancellationToken ct)
    {
        var inv = await _inventory.Find(i => i.ProductId == productId).FirstOrDefaultAsync(ct);
        return inv is null ? NotFound() : Ok(inv);
    }

    [HttpPost]
    public async Task<IActionResult> Create([FromBody] Inventory inv, CancellationToken ct)
    {
        inv.Id        = null;
        inv.UpdatedAt = DateTime.UtcNow;

        // Upsert so POST is idempotent if called twice for the same product
        await _inventory.ReplaceOneAsync(
            i => i.ProductId == inv.ProductId,
            inv,
            new ReplaceOptions { IsUpsert = true },
            ct);

        return CreatedAtAction(nameof(GetByProductId), new { productId = inv.ProductId }, inv);
    }

    [HttpPatch("{productId}")]
    public async Task<IActionResult> Patch(
        string productId,
        [FromBody] PatchInventoryDto patch,
        CancellationToken ct)
    {
        var result = await _inventory.UpdateOneAsync(
            i => i.ProductId == productId,
            Builders<Inventory>.Update
                .Set(i => i.StockQuantity, patch.StockQuantity)
                .Set(i => i.UpdatedAt, DateTime.UtcNow),
            cancellationToken: ct);

        return result.MatchedCount == 0 ? NotFound() : NoContent();
    }
}
