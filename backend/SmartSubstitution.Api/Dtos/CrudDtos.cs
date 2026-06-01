namespace SmartSubstitution.Api.Dtos;

public record PatchProductDto(bool? IsActive, double? BasePrice);

public record PatchInventoryDto(int StockQuantity);
