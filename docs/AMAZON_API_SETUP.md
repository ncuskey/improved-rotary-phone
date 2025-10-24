# Amazon Product Advertising API Setup

The system can now fetch real-time Amazon pricing and sales rank data using the Amazon Product Advertising API (PA-API 5.0).

## Features

When Amazon API credentials are configured, the system will automatically fetch:
- **Lowest Amazon Price** (new and used) - Shows what customers are paying on Amazon
- **Sales Rank** - Current Amazon bestseller rank
- **Offers Count** - Number of sellers offering the item
- **Availability** - Current availability status

This data is merged into BookScouter results and used in:
- **Price Estimation**: Amazon lowest price informs eBay sale price estimates (70% of Amazon price)
- **Probability Scoring**: Sales rank improves confidence in market demand
- **Decision Making**: Real-time pricing vs. buyback offers

## Getting API Credentials

### 1. Join Amazon Associates Program
1. Go to [Amazon Associates](https://affiliate-program.amazon.com/)
2. Sign up for an account (free)
3. Get your **Associate Tag** (Partner Tag)
   - Example: `yourname-20`

### 2. Sign up for Product Advertising API
1. Go to [Amazon Product Advertising API](https://webservices.amazon.com/paapi5/documentation/)
2. Sign in with your Associate account
3. Request PA-API access (requires Associates account with qualifying traffic)
4. Once approved, go to [Security Credentials](https://aws.amazon.com/console/)
5. Generate **Access Key ID** and **Secret Access Key**
   - Keep these secure!

### 3. Configure Environment Variables

Add these to your `.env` file in the project root:

```bash
# Amazon Product Advertising API (PA-API 5.0)
AMAZON_ACCESS_KEY=your_access_key_here
AMAZON_SECRET_KEY=your_secret_key_here
AMAZON_PARTNER_TAG=yourname-20
```

**That's it!** The system will automatically use Amazon API when credentials are present.

## Usage

Once configured, Amazon pricing is automatically fetched:

```python
from isbn_lot_optimizer.service import BookService

service = BookService(database_path="catalog.db")

# Scan a book - automatically includes Amazon pricing
eval = service.scan_isbn("9780345299062", condition="Good")

if eval.bookscouter and eval.bookscouter.amazon_lowest_price:
    print(f"Amazon lowest: ${eval.bookscouter.amazon_lowest_price:.2f}")
    print(f"Estimated eBay price: ${eval.estimated_price:.2f}")
    # Estimated price now uses 70% of Amazon price as anchor
```

## API Limits

Amazon PA-API has rate limits:
- **1 request/second** steady-state
- **10 request burst** allowed
- Daily limits vary by account tier

The system respects these limits by:
- Only calling Amazon API during book scans (not for existing books)
- Caching results in the database
- Gracefully failing if limits exceeded (falls back to BookScouter-only data)

## Without Credentials

If Amazon credentials are not configured:
- System works normally using BookScouter + eBay data only
- No errors are raised
- Amazon pricing fields remain `None`
- Price estimates use eBay comps and metadata only

## Benefits

### Before Amazon API:
```
Title: XPD
Estimated Price: $11.20  (based on metadata heuristics)
Buyback: $0.04
```

### After Amazon API:
```
Title: XPD
Amazon Lowest: $5.68
Estimated Price: $3.78  (70% of Amazon price, Good condition)
Buyback: $0.04
```

Now you can see that XPD sells for $5.68 on Amazon, so a realistic eBay estimate is ~$3.78, making the $0.04 buyback offer clearly unprofitable.

## Troubleshooting

### "Amazon API credentials required" error
- Ensure all 3 environment variables are set in `.env`
- Restart the application after setting variables

### No Amazon data being fetched
- Check that you have PA-API access (not just Associates membership)
- Verify credentials are correct (test with Amazon's API explorer)
- Check logs for API errors

### Rate limit exceeded
- Reduce scanning frequency
- Amazon data is cached in database - re-scanning same books won't hit API again

## Security

**Never commit credentials to git!**

The `.env` file should be in `.gitignore`. Keep your Secret Access Key private.

## More Information

- [PA-API 5.0 Documentation](https://webservices.amazon.com/paapi5/documentation/)
- [Amazon Associates](https://affiliate-program.amazon.com/)
- [AWS IAM Best Practices](https://docs.aws.amazon.com/IAM/latest/UserGuide/best-practices.html)
