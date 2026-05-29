namespace SmartSubstitution.Api.Dtos;

// ── Outbound: .NET → Python ──────────────────────────────────────────────────

public record PythonCompanyDto(string Id, string Name);

public record PythonProductDto(
    string Id,
    string Name,
    string CategoryId,
    string Brand,
    string Unit,
    double PackSize,
    double BasePrice,
    List<string> DietaryTags);

public record PythonContractItemDto(
    string ProductId,
    double ContractPrice,
    bool IsPreferred);

public record PythonCandidateProductDto(
    string Id,
    string Name,
    string CategoryId,
    string Brand,
    string Unit,
    double PackSize,
    double BasePrice,
    int StockQuantity,
    double? ContractPrice,
    bool IsActive,
    List<string> DietaryTags);

public record PythonReplacementRequestDto(
    PythonCompanyDto Company,
    PythonProductDto RequestedProduct,
    int RequestedQuantity,
    List<PythonContractItemDto> ContractItems,
    List<PythonCandidateProductDto> CandidateProducts,
    int MaxResults,
    bool UseAiExplanation);

// ── Inbound: Python → .NET ───────────────────────────────────────────────────
// All properties deserialized from snake_case via SnakeCaseNamingPolicy.

public record PythonScoreBreakdownDto(
    int CategorySimilarity,
    int ContractMatch,
    int PriceSimilarity,
    int StockAvailability,
    int UnitPackSimilarity);

public record PythonReplacementDto(
    string ProductId,
    string Name,
    int FinalScore,
    int ConfidencePct,
    string ConfidenceLabel,
    PythonScoreBreakdownDto ScoreBreakdown,
    string Explanation);

public record PythonRejectedCandidateDto(
    string ProductId,
    string Name,
    string RejectionReason);

public record PythonReplacementResponseDto(
    List<PythonReplacementDto> Replacements,
    List<PythonRejectedCandidateDto> RejectedCandidates,
    string? NoCandidatesReason);
