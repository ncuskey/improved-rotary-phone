# Amazon Product Advertising API Setup Guide

**Stop wasting Decodo credits on Amazon!** Switch to the free official API.

---

## Why Amazon PA-API?

### Current (Expensive):
- ❌ Using Decodo **Advanced credits** (limited to 4.5K remaining)
- ❌ 1 credit per ISBN lookup
- ❌ Already used 18.5K credits on Amazon data

### With PA-API (Free):
- ✅ **FREE** for Amazon Associates with qualifying sales
- ✅ 8,640 requests per day (free tier)
- ✅ Official, stable, structured JSON
- ✅ Same data: rank, price, rating, reviews, details
- ✅ Save Decodo credits for sites without APIs (AbeBooks!)

**Savings**: Switch now and save 90K Core credits + remaining Advanced credits!

---

## Prerequisites

### 1. Amazon Associates Account

You need an Amazon Associates account to access PA-API.

**Sign up**: https://affiliate-program.amazon.com

**Requirements**:
- Website or mobile app (can be your business site)
- Valid tax information
- Must generate qualifying sales within 180 days to maintain access

**Note**: PA-API access is granted automatically upon Associates approval.

---

### 2. Get PA-API Credentials

Once approved as an Associate:

1. **Login to Associates Central**: https://affiliate-program.amazon.com
2. **Navigate to Tools** → **Product Advertising API**
3. **Create credentials**:
   - Access Key ID
   - Secret Access Key
   - Associate Tag (your tracking ID)

**Save these securely** - you'll need all three.

---

## API Tiers & Limits

### Free Tier (Standard)
- **Rate**: 1 request per second
- **Quota**: 8,640 requests per day
- **Requirements**: Amazon Associates account with qualifying sales

### Growth Tier (Higher Limits)
- Up to 36,000 requests per day
- Requires higher sales volume
- Automatic upgrade when eligible

**For your needs**: Free tier is sufficient (750 books × multiple refreshes per month)

---

## Installation

### Install Python SDK

```bash
pip install amazon-paapi
```

Or add to your requirements.txt:
```
amazon-paapi>=5.0.0
```

---

## Configuration

### Add credentials to .env file

```bash
# Amazon Product Advertising API (PA-API)
AMAZON_ACCESS_KEY=AKIAIOSFODNN7EXAMPLE
AMAZON_SECRET_KEY=wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY
AMAZON_ASSOCIATE_TAG=yourtag-20
AMAZON_REGION=us-east-1
```

**Replace with your actual credentials!**

---

## Implementation

See `shared/amazon_paapi.py` for complete implementation.

### Key Features:
- ISBN-10 and ISBN-13 lookup
- Automatic retry with exponential backoff
- Rate limiting (respects 1 req/sec limit)
- Error handling and logging
- Extracts all ML-relevant features

---

## Usage Examples

### Single Book Lookup

```python
from shared.amazon_paapi import fetch_amazon_data

# Lookup by ISBN
data = fetch_amazon_data("9780553381702")

print(f"Title: {data['title']}")
print(f"Amazon Rank: {data['amazon_sales_rank']}")
print(f"Price: ${data['amazon_lowest_price']}")
print(f"Rating: {data['amazon_rating']}")
print(f"Reviews: {data['amazon_ratings_count']}")
```

### Bulk Collection

```python
from shared.amazon_paapi import fetch_amazon_bulk

isbns = ["9780553381702", "9780439708180", ...]
results = fetch_amazon_bulk(isbns)

for isbn, data in results.items():
    if data.get('amazon_sales_rank'):
        print(f"{isbn}: Rank {data['amazon_sales_rank']}")
```

### Command Line Tool

```bash
# Test single ISBN
python3 scripts/collect_amazon_paapi.py --isbn 9780553381702

# Bulk collection from database
python3 scripts/collect_amazon_paapi.py --limit 100

# From file
python3 scripts/collect_amazon_paapi.py --isbn-file isbns.txt
```

---

## Data Comparison: Decodo vs PA-API

| Feature | Decodo | PA-API | Winner |
|---------|--------|--------|--------|
| **Cost** | 1 credit/request | FREE | 🏆 PA-API |
| **Rate Limit** | 30 req/sec | 1 req/sec | Decodo |
| **Daily Quota** | Credit-based | 8,640/day | Both OK |
| **Data Format** | JSON | JSON | Tie |
| **Reliability** | Good | Official | 🏆 PA-API |
| **Stability** | May change | Versioned | 🏆 PA-API |
| **Setup Time** | 5 minutes | 15 minutes | Decodo |

**Verdict**: PA-API is clearly better for Amazon data!

---

## Migration Plan

### Phase 1: Setup (15 minutes)
1. ✅ Apply for Amazon Associates (if not already)
2. ✅ Get PA-API credentials
3. ✅ Add to .env file
4. ✅ Install python package: `pip install amazon-paapi`
5. ✅ Test with single ISBN

### Phase 2: Test (30 minutes)
1. Run test script with 10 ISBNs
2. Verify data quality matches Decodo
3. Compare feature extraction
4. Validate database storage

### Phase 3: Switch (Immediate)
1. Update all collection scripts to use PA-API
2. Stop using Decodo for Amazon lookups
3. Reserve Decodo credits for AbeBooks

### Phase 4: Backfill (1-2 days)
1. Identify ISBNs missing Amazon data
2. Run bulk collection with PA-API
3. No credit cost!

---

## Rate Limiting Best Practices

PA-API limits: **1 request per second**

```python
import time

def collect_with_rate_limit(isbns):
    for isbn in isbns:
        data = fetch_amazon_data(isbn)
        time.sleep(1.0)  # Respect 1 req/sec limit
```

**Daily capacity**:
- 1 req/sec × 60 sec × 60 min × 24 hr = 86,400 theoretical
- Actual limit: 8,640 per day (10% of theoretical)
- Your needs: ~750 books = 8.6% of daily quota

**Conclusion**: You can refresh all books daily with room to spare!

---

## Error Handling

### Common Errors

**1. ItemNotAccessibleByYourAccount**
- Item not available in PA-API
- Use alternative data source

**2. TooManyRequests**
- Hit rate limit (1 req/sec)
- Implement exponential backoff
- Reduce request frequency

**3. InvalidSignature**
- Credentials incorrect
- Check Access Key, Secret Key, and region

**4. NoResults**
- ISBN not found in Amazon catalog
- Try ISBN-10 if ISBN-13 fails
- Book may not be available on Amazon

---

## Cost Savings Calculator

### Current Decodo Cost (Historical)
- Amazon lookups: 18,500 Advanced credits used
- Advanced credit cost: ~$0.01-0.02 per credit (estimated)
- **Total spent: ~$185-370**

### PA-API Cost
- Setup: Free
- Requests: Free (with Associates account)
- Maintenance: Free
- **Total cost: $0**

### Future Savings
- 750 books × 12 refreshes/year = 9,000 requests/year
- Decodo cost: 9,000 credits = $90-180/year
- PA-API cost: $0/year
- **Annual savings: $90-180**

**ROI**: Setup pays for itself immediately!

---

## Associates Account Maintenance

To maintain PA-API access, your Associates account must remain active:

**Requirements**:
- Generate at least 3 qualifying sales within 180 days of approval
- Continue generating sales to maintain active status
- If inactive, account may be closed (but can reapply)

**Strategies**:
1. Add Amazon affiliate links to your business website
2. Link to relevant books in blog posts/documentation
3. Share useful book recommendations with affiliate links
4. Normal business operations may generate qualifying traffic

**Fallback**: If Associates account closes, you can:
- Reapply for Associates
- Use Decodo as backup (but much more expensive)
- Use alternative APIs (ISBNdb, Google Books, etc.)

---

## Testing Checklist

Before switching production scripts:

- [ ] Amazon Associates account approved
- [ ] PA-API credentials obtained (Access Key, Secret Key, Tag)
- [ ] Credentials added to .env file
- [ ] Python package installed (`amazon-paapi`)
- [ ] Test script runs successfully with 1 ISBN
- [ ] Data structure matches expected format
- [ ] All ML features extracted correctly
- [ ] Rate limiting works (no TooManyRequests errors)
- [ ] Error handling works for invalid ISBNs
- [ ] Database integration tested

**Only proceed to bulk collection after all checks pass ✅**

---

## Support Resources

- **PA-API Documentation**: https://webservices.amazon.com/paapi5/documentation/
- **Associates Central**: https://affiliate-program.amazon.com
- **Python SDK Docs**: https://github.com/sergioteula/python-amazon-paapi
- **Support Forum**: https://forums.aws.amazon.com/forum.jspa?forumID=9

---

## Next Steps

1. **Apply for Amazon Associates**: https://affiliate-program.amazon.com (if needed)
2. **Get PA-API credentials**: Associates Central → Tools → PA-API
3. **Add to .env**: `AMAZON_ACCESS_KEY`, `AMAZON_SECRET_KEY`, `AMAZON_ASSOCIATE_TAG`
4. **Install package**: `pip install amazon-paapi`
5. **Test**: `python3 scripts/test_amazon_paapi.py`
6. **Migrate**: Switch collection scripts to PA-API
7. **Celebrate**: You just saved thousands of Decodo credits! 🎉

---

## Summary

**Stop using Decodo for Amazon immediately!**

- You've already spent 18.5K Advanced credits on Amazon
- PA-API provides same data for FREE
- Save remaining 4.5K Advanced credits for emergencies
- Use 90K Core credits for AbeBooks (no free alternative)

**This single change could save you $90-180 per year** in ongoing Decodo costs!
