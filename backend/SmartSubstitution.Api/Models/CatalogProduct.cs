using System.Text.Json.Serialization;
using MongoDB.Bson;
using MongoDB.Bson.Serialization.Attributes;

namespace SmartSubstitution.Api.Models;

// ── Composite _id ─────────────────────────────────────────────────────────────

public class CatalogProductId
{
    public string ItemNumber { get; set; } = null!;
    public string SellerAccountNumber { get; set; } = null!;
    public string ContractNumber { get; set; } = null!;
}

// ── Campaign (nested inside Price) ────────────────────────────────────────────

[BsonIgnoreExtraElements]
public class CampaignInfo
{
    public DateTime? From { get; set; }
    public DateTime? To { get; set; }
    public string? Description { get; set; }
    public string CampaignPrice { get; set; } = null!;
    public int CampaignType { get; set; }
}

// ── Price (nested inside PartType) ────────────────────────────────────────────

[BsonIgnoreExtraElements]
public class PartTypePrice
{
    /// <summary>Total pack price as a string, e.g. "562.5000"</summary>
    public string Price { get; set; } = null!;
    public string? PriceBeforeCampaign { get; set; }
    public DateTime Updated { get; set; }

    /// <summary>Price per UnitPriceType (e.g. per KG)</summary>
    public string UnitPrice { get; set; } = null!;
    public string UnitPriceType { get; set; } = null!;
    public bool PriceOption { get; set; }
    public string PriceBeforeDiscount { get; set; } = null!;
    public string MinQty { get; set; } = null!;
    public string MaxQty { get; set; } = null!;
    public string QtyStep { get; set; } = null!;
    public string AlcoFee { get; set; } = null!;
    public CampaignInfo? Campaign { get; set; }

    [BsonIgnore]
    public decimal UnitPriceDecimal =>
        decimal.TryParse(UnitPrice, System.Globalization.NumberStyles.Number,
            System.Globalization.CultureInfo.InvariantCulture, out var v) ? v : 0m;
}

// ── PartType (TU = trade unit / CU = consumer unit) ──────────────────────────

[BsonIgnoreExtraElements]
public class PartType
{
    /// <summary>Number of CU units inside this pack type, e.g. "15.0000"</summary>
    public string NumberInUnit { get; set; } = null!;
    public string Unit { get; set; } = null!;

    /// <summary>TU = trade/pack unit, CU = consumer/each unit</summary>
    public string Code { get; set; } = null!;
    public int Rank { get; set; }
    public PartTypePrice Price { get; set; } = null!;
    public string? Description { get; set; }
}

// ── StockArea ─────────────────────────────────────────────────────────────────

[BsonIgnoreExtraElements]
public class StockArea
{
    public string StockAreaId { get; set; } = null!;
    public bool Available { get; set; }
    public int LeadTime { get; set; }
    public string? Transport { get; set; }
    public string? OrderGroupCode { get; set; }

    /// <summary>Which PartType this entry covers (CU or TU)</summary>
    public string PartType { get; set; } = null!;
}

// ── StockAreaFilter ───────────────────────────────────────────────────────────

[BsonIgnoreExtraElements]
public class StockAreaFilter
{
    public string StockAreaId { get; set; } = null!;
    public bool Available { get; set; }
    public string PartType { get; set; } = null!;
}

// ── ExtraItemInfo — { k: "GPC", v: ["10005889"] } ────────────────────────────

public class ExtraItemInfoEntry
{
    [BsonElement("k")]
    public string Key { get; set; } = null!;

    [BsonElement("v")]
    public List<string> Values { get; set; } = new();
}

// ── MeasurementInfo ───────────────────────────────────────────────────────────

public class CatalogMeasurementInfo
{
    public string MeasurementCode { get; set; } = null!;

    /// <summary>Base measurement quantity, e.g. "1.0000"</summary>
    public string Measurement { get; set; } = null!;
}

// ── Klimato CO₂ mapping ───────────────────────────────────────────────────────

public class KlimatoMapping
{
    public string UnitAccountNumber { get; set; } = null!;
    public double Co2ePerKg { get; set; }
    public int Co2Level { get; set; }
}

// ── Root document ─────────────────────────────────────────────────────────────

[BsonIgnoreExtraElements]
public class CatalogProduct
{
    [BsonId]
    public CatalogProductId Id { get; set; } = null!;

    public string Name { get; set; } = null!;
    public string? Description { get; set; }
    public string? Eanno { get; set; }
    public string? ImageUrl { get; set; }
    public string? LongDescriptionUrl { get; set; }
    public string? ItemNumberProducer { get; set; }
    public string SellerName { get; set; } = null!;
    public string SellerAccountNumber { get; set; } = null!;
    public string ContractNumber { get; set; } = null!;
    public string? ProducerName { get; set; }
    public string ItemNumber { get; set; } = null!;
    public string? OldItemNumber { get; set; }
    public bool HasMatInfo { get; set; }
    public string? ChangedById { get; set; }

    [BsonIgnoreIfNull]
    [JsonIgnore]
    public BsonValue? Information { get; set; }

    [JsonIgnore] public List<BsonDocument> Markings { get; set; } = new();
    public List<ExtraItemInfoEntry> ExtraItemInfo { get; set; } = new();
    [JsonIgnore] public List<BsonDocument> ExtraOrderInfo { get; set; } = new();
    public List<PartType> PartTypes { get; set; } = new();
    [BsonIgnore][JsonIgnore] public List<string> ExtraItemNumbers { get; set; } = new();
    [BsonIgnore][JsonIgnore] public List<string> ExtraItemNumbersFilters { get; set; } = new();
    [JsonIgnore] public List<BsonDocument> AddonItems { get; set; } = new();
    public string? CustomSearchWords { get; set; }
    public List<StockArea> StockAreas { get; set; } = new();
    public bool OnlyAddonItem { get; set; }
    public bool Internal { get; set; }
    public CatalogMeasurementInfo? MeasurementInfo { get; set; }
    public int LeadTime { get; set; }
    public string? AssortmentCode { get; set; }
    public string? Substitute { get; set; }
    public DateTime? DateExpired { get; set; }
    public int Expired { get; set; }
    public string? ExpiredReason { get; set; }
    public DateTime Changed { get; set; }
    public bool Bonus { get; set; }
    public bool Bonus2 { get; set; }
    public bool PreferredProduct { get; set; }
    public int DiscountType { get; set; }
    public List<string> CatalogCategories { get; set; } = new();
    public List<string> MainCatalogCategories { get; set; } = new();

    /// <summary>Pipe-delimited category path, e.g. "|-|Frukt|-|APPELSIN"</summary>
    public List<string> CategoryPaths { get; set; } = new();

    public string? CatalogName { get; set; }
    public string? SearchData { get; set; }
    [JsonIgnore] public List<BsonDocument> CustomUnitInfo { get; set; } = new();
    public bool HasStockAreas { get; set; }
    public bool HasValidoo { get; set; }
    public bool HasDabas { get; set; }
    public double Score { get; set; }
    public bool IgnoreOutOfStock { get; set; }
    public bool InventoryAvailabilityControlled { get; set; }

    [BsonIgnoreIfNull]
    [JsonIgnore]
    public BsonValue? InventoryAvailability { get; set; }

    public List<StockAreaFilter> StockAreaFilters { get; set; } = new();
    public string? OriginCountry { get; set; }
    public string? OrderGroupCode { get; set; }
    public bool HasKlimato { get; set; }
    public List<KlimatoMapping> KlimatoMappings { get; set; } = new();

    // ── Derived helpers (not persisted) ──────────────────────────────────────

    /// <summary>True when the product is not expired and has no expiry date set.</summary>
    [BsonIgnore]
    public bool IsActive => Expired == 0 && DateExpired == null;

    /// <summary>
    /// Consumer unit — individual piece. Code=="CU" when present;
    /// fallback: the PartType with the smallest NumberInUnit (CU always has NumberInUnit=1).
    /// </summary>
    [BsonIgnore]
    public PartType? ConsumerUnit =>
        PartTypes.FirstOrDefault(p => p.Code == "CU")
        ?? PartTypes.OrderBy(p => ParseNiu(p.NumberInUnit)).FirstOrDefault();

    /// <summary>
    /// Trade/pack unit — whole package (NumberInUnit > 1, e.g. 6, 10, 15).
    /// Code=="TU" when present; fallback: PartType with the largest NumberInUnit.
    /// </summary>
    [BsonIgnore]
    public PartType? TradeUnit =>
        PartTypes.FirstOrDefault(p => p.Code == "TU")
        ?? PartTypes.Where(p => ParseNiu(p.NumberInUnit) > 1)
                    .OrderByDescending(p => ParseNiu(p.NumberInUnit))
                    .FirstOrDefault();

    /// <summary>Normalised unit price (per KG / per piece) from the CU part type.</summary>
    [BsonIgnore]
    public decimal UnitPrice => ConsumerUnit?.Price.UnitPriceDecimal ?? 0m;

    /// <summary>
    /// True when the product can be ordered (any PartType has available stock).
    /// Falls back to IsActive when no StockAreas are recorded.
    /// </summary>
    [BsonIgnore]
    public bool IsAvailable =>
        StockAreas.Count > 0
            ? StockAreas.Any(s => s.Available)
            : IsActive;

    /// <summary>
    /// CU is available. When StockAreas are present, checks for a CU StockArea with
    /// Available=true. When absent (most suppliers don't publish stock areas), falls back
    /// to checking whether the product actually has a PartType that can be ordered as a
    /// single unit (NumberInUnit ≤ 1) — e.g. a product sold only in packs of 6 or 10
    /// has no CU format and returns false.
    /// </summary>
    [BsonIgnore]
    public bool IsCuAvailable =>
        StockAreas.Count > 0
            ? StockAreas.Any(s => s.PartType == "CU" && s.Available)
            : IsActive && PartTypes.Any(p => ParseNiu(p.NumberInUnit) <= 1);

    /// <summary>
    /// TU is available. When StockAreas are present, checks for a TU StockArea with
    /// Available=true. When absent, falls back to checking whether the product has a
    /// PartType sold as a package (NumberInUnit > 1).
    /// </summary>
    [BsonIgnore]
    public bool IsTuAvailable =>
        StockAreas.Count > 0
            ? StockAreas.Any(s => s.PartType == "TU" && s.Available)
            : IsActive && PartTypes.Any(p => ParseNiu(p.NumberInUnit) > 1);

    /// <summary>Whether any StockArea for the given stockAreaId reports Available.</summary>
    public bool IsAvailableIn(string stockAreaId) =>
        StockAreas.Any(s => s.StockAreaId == stockAreaId && s.Available);

    private static decimal ParseNiu(string? s) =>
        decimal.TryParse(s, System.Globalization.NumberStyles.Number,
            System.Globalization.CultureInfo.InvariantCulture, out var v) ? v : 0m;
}
