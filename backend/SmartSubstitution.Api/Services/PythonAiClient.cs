using System.Text;
using System.Text.Json;
using Microsoft.Extensions.Options;
using SmartSubstitution.Api.Dtos;
using SmartSubstitution.Api.Settings;

namespace SmartSubstitution.Api.Services;

public class PythonAiClient
{
    private readonly HttpClient _http;
    private static readonly JsonSerializerOptions _snakeOptions = new()
    {
        PropertyNamingPolicy = SnakeCaseNamingPolicy.Instance,
        PropertyNameCaseInsensitive = true,
    };

    public PythonAiClient(HttpClient http)
    {
        _http = http;
    }

    public async Task<PythonReplacementResponseDto?> GetReplacementsAsync(
        PythonReplacementRequestDto request,
        CancellationToken ct = default)
    {
        var json = JsonSerializer.Serialize(request, _snakeOptions);
        using var content = new StringContent(json, Encoding.UTF8, "application/json");

        var response = await _http.PostAsync("/recommendations/replacements", content, ct);
        response.EnsureSuccessStatusCode();

        var body = await response.Content.ReadAsStringAsync(ct);
        return JsonSerializer.Deserialize<PythonReplacementResponseDto>(body, _snakeOptions);
    }
}
