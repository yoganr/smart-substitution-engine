namespace SmartSubstitution.Api.Dtos;

// ── Client-facing request/response ──────────────────────────────────────────

/// <summary>
/// Product identifier — matches the composite _id in the catalog:
/// { ItemNumber, SellerAccountNumber, ContractNumber }.
/// </summary>
public record ProductIdentifierDto(
    string ItemNumber,
    string SellerAccountNumber,
    string ContractNumber);

/// <summary>
/// Optional preferred ordering unit. "CU" = individual piece (NumberInUnit=1),
/// "TU" = whole package (NumberInUnit>1, e.g. 10). Null means no preference.
/// When specified, replacement is triggered even if the product is "in stock"
/// but only available in the other PartType.
/// </summary>
public record ReplacementRequestDto(
    ProductIdentifierDto Product,
    List<string> ContractNumbers,
    int RequestedQuantity,
    int MaxResults = 3,
    bool UseAiExplanation = true,
    string? PreferredPartType = null);

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
