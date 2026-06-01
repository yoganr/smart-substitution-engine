using Microsoft.AspNetCore.Mvc;
using MongoDB.Driver;
using SmartSubstitution.Api.Models;

namespace SmartSubstitution.Api.Controllers;

[ApiController]
[Route("[controller]")]
public class CompaniesController : ControllerBase
{
    private readonly IMongoCollection<Company>  _companies;
    private readonly IMongoCollection<Contract> _contracts;

    public CompaniesController(IMongoDatabase db)
    {
        _companies = db.GetCollection<Company>("companies");
        _contracts = db.GetCollection<Contract>("contracts");
    }

    [HttpGet]
    public async Task<IActionResult> GetAll(CancellationToken ct)
    {
        var result = await _companies.Find(_ => true).ToListAsync(ct);
        return Ok(result);
    }

    [HttpGet("{companyId}")]
    public async Task<IActionResult> GetById(string companyId, CancellationToken ct)
    {
        var company = await _companies.Find(c => c.CompanyId == companyId).FirstOrDefaultAsync(ct);
        return company is null ? NotFound() : Ok(company);
    }

    [HttpPost]
    public async Task<IActionResult> Create([FromBody] Company company, CancellationToken ct)
    {
        company.Id = null;
        await _companies.InsertOneAsync(company, cancellationToken: ct);
        return CreatedAtAction(nameof(GetById), new { companyId = company.CompanyId }, company);
    }

    [HttpGet("{companyId}/contracts")]
    public async Task<IActionResult> GetContracts(string companyId, CancellationToken ct)
    {
        var result = await _contracts.Find(c => c.CompanyId == companyId).ToListAsync(ct);
        return Ok(result);
    }
}
