using Microsoft.AspNetCore.Mvc;
using MongoDB.Driver;
using SmartSubstitution.Api.Models;

namespace SmartSubstitution.Api.Controllers;

[ApiController]
[Route("[controller]")]
public class ContractsController : ControllerBase
{
    private readonly IMongoCollection<Contract> _contracts;

    public ContractsController(IMongoDatabase db)
        => _contracts = db.GetCollection<Contract>("contracts");

    [HttpPost]
    public async Task<IActionResult> Create([FromBody] Contract contract, CancellationToken ct)
    {
        contract.Id = null;
        await _contracts.InsertOneAsync(contract, cancellationToken: ct);
        return CreatedAtAction(nameof(GetById), new { contractId = contract.ContractId }, contract);
    }

    [HttpGet("{contractId}")]
    public async Task<IActionResult> GetById(string contractId, CancellationToken ct)
    {
        var contract = await _contracts.Find(c => c.ContractId == contractId).FirstOrDefaultAsync(ct);
        return contract is null ? NotFound() : Ok(contract);
    }

    [HttpPost("{contractId}/items")]
    public async Task<IActionResult> AddItem(
        string contractId,
        [FromBody] ContractItem item,
        CancellationToken ct)
    {
        var result = await _contracts.UpdateOneAsync(
            c => c.ContractId == contractId,
            Builders<Contract>.Update.Push(c => c.Items, item),
            cancellationToken: ct);

        return result.MatchedCount == 0 ? NotFound() : Ok(new { message = "Item added" });
    }
}
