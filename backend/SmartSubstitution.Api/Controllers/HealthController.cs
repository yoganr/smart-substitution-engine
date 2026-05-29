using Microsoft.AspNetCore.Mvc;
using MongoDB.Driver;

namespace SmartSubstitution.Api.Controllers;

[ApiController]
[Route("[controller]")]
public class HealthController : ControllerBase
{
    private readonly IMongoDatabase _db;

    public HealthController(IMongoDatabase db)
    {
        _db = db;
    }

    [HttpGet]
    public async Task<IActionResult> Get()
    {
        try
        {
            await _db.RunCommandAsync<object>("{ ping: 1 }");
            return Ok(new { status = "ok", database = "connected" });
        }
        catch (Exception ex)
        {
            return StatusCode(503, new { status = "degraded", database = "unreachable", error = ex.Message });
        }
    }
}
