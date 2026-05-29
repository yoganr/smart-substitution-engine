using Microsoft.Extensions.Options;
using MongoDB.Driver;
using SmartSubstitution.Api.Repositories;
using SmartSubstitution.Api.Services;
using SmartSubstitution.Api.Settings;

var builder = WebApplication.CreateBuilder(args);

// ── Settings ─────────────────────────────────────────────────────────────────

builder.Services.Configure<MongoDbSettings>(
    builder.Configuration.GetSection("MongoDB"));

builder.Services.Configure<PythonAiSettings>(
    builder.Configuration.GetSection("PythonAiService"));

// ── MongoDB — Singleton (CRITICAL: Scoped/Transient exhausts Atlas M0 pool) ──

builder.Services.AddSingleton<IMongoClient>(sp =>
{
    var settings = sp.GetRequiredService<IOptions<MongoDbSettings>>().Value;
    return new MongoClient(settings.ConnectionString);
});

builder.Services.AddScoped<IMongoDatabase>(sp =>
{
    var settings = sp.GetRequiredService<IOptions<MongoDbSettings>>().Value;
    var client = sp.GetRequiredService<IMongoClient>();
    return client.GetDatabase(settings.DatabaseName);
});

// ── Application services ─────────────────────────────────────────────────────

builder.Services.AddScoped<CandidateProductService>();

builder.Services.AddHttpClient<PythonAiClient>((sp, http) =>
{
    var settings = sp.GetRequiredService<IOptions<PythonAiSettings>>().Value;
    http.BaseAddress = new Uri(settings.BaseUrl);
    http.Timeout = TimeSpan.FromSeconds(settings.TimeoutSeconds);
});

// ── Controllers + Swagger ─────────────────────────────────────────────────────

builder.Services.AddControllers();
builder.Services.AddEndpointsApiExplorer();
builder.Services.AddSwaggerGen();

var app = builder.Build();

// ── Ensure MongoDB indexes on startup ─────────────────────────────────────────

using (var scope = app.Services.CreateScope())
{
    var db = scope.ServiceProvider.GetRequiredService<IMongoDatabase>();
    try
    {
        await MongoIndexes.EnsureIndexesAsync(db);
    }
    catch (Exception ex)
    {
        var logger = scope.ServiceProvider.GetRequiredService<ILogger<Program>>();
        logger.LogWarning(ex, "Could not ensure MongoDB indexes — Atlas may not be configured yet");
    }
}

// ── Middleware ─────────────────────────────────────────────────────────────────

app.UseSwagger();
app.UseSwaggerUI();
app.UseAuthorization();
app.MapControllers();

app.Run();
