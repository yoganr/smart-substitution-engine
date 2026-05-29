namespace SmartSubstitution.Api.Dtos;

// ── Client-facing request/response ──────────────────────────────────────────

public record ReplacementRequestDto(
    string CompanyId,
    string ProductId,
    int RequestedQuantity,
    int MaxResults = 3,
    bool UseAiExplanation = true);

public record ScoreBreakdownDto(
    int CategorySimilarity,
    int ContractMatch,
    int PriceSimilarity,
    int StockAvailability,
    int UnitPackSimilarity);

public record ReplacementDto(
    string ProductId,
    string Name,
    int FinalScore,
    int ConfidencePct,
    string ConfidenceLabel,
    ScoreBreakdownDto ScoreBreakdown,
    string Explanation);

public record RejectedCandidateDto(
    string ProductId,
    string Name,
    string RejectionReason);

public record ReplacementResponseDto(
    bool ReplacementNeeded,
    List<ReplacementDto>? Replacements = null,
    List<RejectedCandidateDto>? RejectedCandidates = null,
    string? NoCandidatesReason = null);
