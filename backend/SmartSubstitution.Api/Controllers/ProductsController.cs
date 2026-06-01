using Microsoft.AspNetCore.Mvc;
using MongoDB.Driver;
using SmartSubstitution.Api.Dtos;
using SmartSubstitution.Api.Models;

namespace SmartSubstitution.Api.Controllers;

[ApiController]
[Route("[controller]")]
public class ProductsController : ControllerBase
{
    private readonly IMongoCollection<Product> _products;

    public ProductsController(IMongoDatabase db)
        => _products = db.GetCollection<Product>("products");

    [HttpGet]
    public async Task<IActionResult> GetAll(
        [FromQuery] string? categoryId,
        [FromQuery] bool? isActive,
        CancellationToken ct)
    {
        var filter = Builders<Product>.Filter.Empty;
        if (categoryId is not null)
            filter &= Builders<Product>.Filter.Eq(p => p.CategoryId, categoryId);
        if (isActive is not null)
            filter &= Builders<Product>.Filter.Eq(p => p.IsActive, isActive.Value);

        var result = await _products.Find(filter).ToListAsync(ct);
        return Ok(result);
    }

    [HttpGet("{productId}")]
    public async Task<IActionResult> GetById(string productId, CancellationToken ct)
    {
        var product = await _products.Find(p => p.ProductId == productId).FirstOrDefaultAsync(ct);
        return product is null ? NotFound() : Ok(product);
    }

    [HttpPost]
    public async Task<IActionResult> Create([FromBody] Product product, CancellationToken ct)
    {
        product.Id = null;
        await _products.InsertOneAsync(product, cancellationToken: ct);
        return CreatedAtAction(nameof(GetById), new { productId = product.ProductId }, product);
    }

    [HttpPatch("{productId}")]
    public async Task<IActionResult> Patch(
        string productId,
        [FromBody] PatchProductDto patch,
        CancellationToken ct)
    {
        var updates = new List<UpdateDefinition<Product>>();
        if (patch.IsActive is not null)
            updates.Add(Builders<Product>.Update.Set(p => p.IsActive, patch.IsActive.Value));
        if (patch.BasePrice is not null)
            updates.Add(Builders<Product>.Update.Set(p => p.BasePrice, patch.BasePrice.Value));

        if (updates.Count == 0)
            return BadRequest(new { error = "No patchable fields provided" });

        var result = await _products.UpdateOneAsync(
            p => p.ProductId == productId,
            Builders<Product>.Update.Combine(updates),
            cancellationToken: ct);

        return result.MatchedCount == 0 ? NotFound() : NoContent();
    }
}
