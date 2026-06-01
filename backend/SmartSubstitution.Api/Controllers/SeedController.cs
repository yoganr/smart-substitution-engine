using Microsoft.AspNetCore.Mvc;
using MongoDB.Driver;
using SmartSubstitution.Api.Models;

namespace SmartSubstitution.Api.Controllers;

[ApiController]
[Route("[controller]")]
public class SeedController : ControllerBase
{
    private readonly IMongoDatabase _db;

    public SeedController(IMongoDatabase db) => _db = db;

    /// <summary>POST /seed — wipe and re-seed all demo collections</summary>
    [HttpPost]
    public async Task<IActionResult> Seed(CancellationToken ct)
    {
        var companies  = _db.GetCollection<Company>("companies");
        var products   = _db.GetCollection<Product>("products");
        var contracts  = _db.GetCollection<Contract>("contracts");
        var inventory  = _db.GetCollection<Inventory>("inventory");

        await companies.DeleteManyAsync(_ => true, ct);
        await products.DeleteManyAsync(_ => true, ct);
        await contracts.DeleteManyAsync(_ => true, ct);
        await inventory.DeleteManyAsync(_ => true, ct);

        // ── Companies ─────────────────────────────────────────────────────────
        await companies.InsertManyAsync(new[]
        {
            new Company { CompanyId = "company_001", Name = "Marco's Italian Kitchen" },
            new Company { CompanyId = "company_002", Name = "The Burger Barn" },
        }, cancellationToken: ct);

        // ── Products ──────────────────────────────────────────────────────────
        await products.InsertManyAsync(new[]
        {
            // Chicken
            new Product { ProductId = "product_001", Name = "Chicken Breast 2kg",          CategoryId = "cat_chicken",    Brand = "Brand A", Unit = "kg", PackSize = 2.0, BasePrice = 10.0, IsActive = true },
            new Product { ProductId = "product_002", Name = "Chicken Breast Premium 2kg",   CategoryId = "cat_chicken",    Brand = "Brand B", Unit = "kg", PackSize = 2.0, BasePrice = 10.5, IsActive = true },
            new Product { ProductId = "product_003", Name = "Chicken Thigh Boneless 2kg",   CategoryId = "cat_chicken",    Brand = "Brand A", Unit = "kg", PackSize = 2.0, BasePrice = 8.5,  IsActive = true },
            new Product { ProductId = "product_004", Name = "Chicken Breast Free Range 2kg",CategoryId = "cat_chicken",    Brand = "Brand C", Unit = "kg", PackSize = 2.0, BasePrice = 12.0, IsActive = true },
            new Product { ProductId = "product_005", Name = "Chicken Breast Frozen 2kg",    CategoryId = "cat_chicken",    Brand = "Brand D", Unit = "kg", PackSize = 2.0, BasePrice = 9.0,  IsActive = true },
            new Product { ProductId = "product_017", Name = "Chicken Breast Organic 2kg",   CategoryId = "cat_chicken",    Brand = "Brand E", Unit = "kg", PackSize = 2.0, BasePrice = 14.0, IsActive = true },
            new Product { ProductId = "product_018", Name = "Chicken Drumsticks 2kg",       CategoryId = "cat_chicken",    Brand = "Brand A", Unit = "kg", PackSize = 2.0, BasePrice = 7.0,  IsActive = true },
            // Beef
            new Product { ProductId = "product_006", Name = "Beef Mince 5% Fat 1kg",        CategoryId = "cat_beef",       Brand = "Brand A", Unit = "kg", PackSize = 1.0, BasePrice = 8.0,  IsActive = true },
            new Product { ProductId = "product_007", Name = "Beef Mince 20% Fat 1kg",       CategoryId = "cat_beef",       Brand = "Brand B", Unit = "kg", PackSize = 1.0, BasePrice = 7.0,  IsActive = true },
            new Product { ProductId = "product_008", Name = "Beef Ribeye Steak 1kg",        CategoryId = "cat_beef",       Brand = "Brand C", Unit = "kg", PackSize = 1.0, BasePrice = 22.0, IsActive = true },
            new Product { ProductId = "product_009", Name = "Beef Burger Patties 1kg",      CategoryId = "cat_beef",       Brand = "Brand D", Unit = "kg", PackSize = 1.0, BasePrice = 9.0,  IsActive = true },
            // Vegetables
            new Product { ProductId = "product_010", Name = "Cherry Tomatoes 5kg",          CategoryId = "cat_vegetables", Brand = "Brand A", Unit = "kg", PackSize = 5.0, BasePrice = 15.0, IsActive = true },
            new Product { ProductId = "product_011", Name = "Beef Tomatoes 5kg",            CategoryId = "cat_vegetables", Brand = "Brand B", Unit = "kg", PackSize = 5.0, BasePrice = 14.0, IsActive = true },
            new Product { ProductId = "product_012", Name = "Iceberg Lettuce 10kg",         CategoryId = "cat_vegetables", Brand = "Brand A", Unit = "kg", PackSize = 10.0, BasePrice = 18.0, IsActive = true },
            new Product { ProductId = "product_013", Name = "Mixed Salad Leaves 2kg",       CategoryId = "cat_vegetables", Brand = "Brand C", Unit = "kg", PackSize = 2.0, BasePrice = 12.0, IsActive = true },
            // Fish
            new Product { ProductId = "product_014", Name = "Salmon Fillet 2kg",            CategoryId = "cat_fish",       Brand = "Brand A", Unit = "kg", PackSize = 2.0, BasePrice = 25.0, IsActive = true },
            new Product { ProductId = "product_015", Name = "Atlantic Cod Fillet 2kg",      CategoryId = "cat_fish",       Brand = "Brand B", Unit = "kg", PackSize = 2.0, BasePrice = 18.0, IsActive = true },
            new Product { ProductId = "product_016", Name = "Sea Bass Fillet 1kg",          CategoryId = "cat_fish",       Brand = "Brand C", Unit = "kg", PackSize = 1.0, BasePrice = 28.0, IsActive = true },
        }, cancellationToken: ct);

        // ── Contracts ─────────────────────────────────────────────────────────
        await contracts.InsertManyAsync(new[]
        {
            new Contract
            {
                ContractId = "contract_001",
                CompanyId  = "company_001",
                Items = new()
                {
                    new ContractItem { ProductId = "product_001", ContractPrice = 9.2,  IsPreferred = true  },
                    new ContractItem { ProductId = "product_002", ContractPrice = 10.0, IsPreferred = false },
                    new ContractItem { ProductId = "product_014", ContractPrice = 24.0, IsPreferred = true  },
                },
            },
            new Contract
            {
                ContractId = "contract_002",
                CompanyId  = "company_002",
                Items = new()
                {
                    new ContractItem { ProductId = "product_006", ContractPrice = 7.5,  IsPreferred = true  },
                    new ContractItem { ProductId = "product_009", ContractPrice = 8.5,  IsPreferred = true  },
                    new ContractItem { ProductId = "product_012", ContractPrice = 17.0, IsPreferred = false },
                },
            },
        }, cancellationToken: ct);

        // ── Inventory ─────────────────────────────────────────────────────────
        // product_001 = 0  → Marco's Italian Kitchen chicken demo triggers replacement
        // product_006 = 0  → The Burger Barn beef demo triggers replacement
        // product_010 = 0  → cherry tomato demo
        await inventory.InsertManyAsync(new[]
        {
            new Inventory { ProductId = "product_001", StockQuantity = 0   },
            new Inventory { ProductId = "product_002", StockQuantity = 150 },
            new Inventory { ProductId = "product_003", StockQuantity = 80  },
            new Inventory { ProductId = "product_004", StockQuantity = 30  },
            new Inventory { ProductId = "product_005", StockQuantity = 200 },
            new Inventory { ProductId = "product_006", StockQuantity = 0   },
            new Inventory { ProductId = "product_007", StockQuantity = 100 },
            new Inventory { ProductId = "product_008", StockQuantity = 50  },
            new Inventory { ProductId = "product_009", StockQuantity = 120 },
            new Inventory { ProductId = "product_010", StockQuantity = 0   },
            new Inventory { ProductId = "product_011", StockQuantity = 180 },
            new Inventory { ProductId = "product_012", StockQuantity = 90  },
            new Inventory { ProductId = "product_013", StockQuantity = 60  },
            new Inventory { ProductId = "product_014", StockQuantity = 25  },
            new Inventory { ProductId = "product_015", StockQuantity = 80  },
            new Inventory { ProductId = "product_016", StockQuantity = 40  },
            new Inventory { ProductId = "product_017", StockQuantity = 20  },
            new Inventory { ProductId = "product_018", StockQuantity = 150 },
        }, cancellationToken: ct);

        return Ok(new
        {
            message          = "Seed complete",
            companies        = 2,
            products         = 17,
            contracts        = 2,
            inventoryEntries = 17,
            demoScenarios    = new[]
            {
                "POST /recommendations/replacements  { companyId: 'company_001', productId: 'product_001', requestedQuantity: 10 }  → chicken replacements",
                "POST /recommendations/replacements  { companyId: 'company_002', productId: 'product_006', requestedQuantity: 5  }  → beef replacements",
            },
        });
    }
}
