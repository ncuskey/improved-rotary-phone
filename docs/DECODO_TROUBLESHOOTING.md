# Decodo Account Troubleshooting Guide

**Date**: October 31, 2025
**Issue**: Getting 429 Rate Limit errors when attempting to scrape with Core plan

---

## Current Situation

### Account Setup
- **Core Plan**: 90K credits (for basic scraping)
- **Advanced Plan**: 23K purchased, ~18.5K used, ~4.5K remaining
- **Problem**: Both plans returning 429 errors
- **Credentials**: `U0000319432` / `PW_1f6d59fd37e51ebf...`

### Error Details
```
HTTP 429: Rate Limit
"Your request couldn't be processed due to rate limits. This may be because:
1) You've used all requests,
2) Your subscription period has ended, or
3) You've exceeded the req/s rate."
```

---

## Troubleshooting Steps

### Step 1: Verify Account Status 🔍

**Action**: Login to Decodo Dashboard
- URL: https://dashboard.decodo.com
- Check subscription status
- Verify credit balance for both plans
- Check expiration dates

**What to Look For**:
- ✅ Core plan: Should show ~90K credits
- ✅ Advanced plan: Should show ~4.5K credits
- ✅ Subscription status: Active
- ✅ Expiration date: Not expired
- ❌ Any warnings or notices

**Screenshot these details for reference**

---

### Step 2: Verify Credentials 🔑

**Check if credentials are for the correct account**:

```bash
# Test credentials
export DECODO_AUTHENTICATION="U0000319432"
export DECODO_PASSWORD="PW_1f6d59fd37e51ebfaf4f26739d59a7adc"

# Check if they work at all
curl -X GET "https://scraper-api.decodo.com/v2/ping" \
  -u "$DECODO_AUTHENTICATION:$DECODO_PASSWORD"
```

**Expected**: 200 OK or similar success response
**If 401**: Credentials are invalid or expired

---

### Step 3: Check Rate Limit Headers 📊

Run this test to see actual rate limit values:

```python
import requests
import base64

username = "U0000319432"
password = "PW_1f6d59fd37e51ebfaf4f26739d59a7adc"

credentials = f"{username}:{password}"
encoded = base64.b64encode(credentials.encode()).decode()

headers = {
    "Authorization": f"Basic {encoded}",
    "Content-Type": "application/json"
}

# Try a simple request
response = requests.post(
    "https://scraper-api.decodo.com/v2/scrape",
    json={
        "target": "universal",
        "url": "https://example.com",
        "render_js": False
    },
    headers=headers,
    timeout=30
)

print(f"Status: {response.status_code}")
print("\nRate Limit Headers:")
for key, value in response.headers.items():
    if 'rate' in key.lower() or 'limit' in key.lower():
        print(f"  {key}: {value}")
```

**What to check**:
- `RateLimit-Remaining`: Should be > 0
- `RateLimit-Reset`: Time until reset
- `RateLimit-Limit`: Your plan's limit

---

### Step 4: Test Different Targets 🎯

**Core plan may support different targets than Advanced**:

Test each target to see which work:

```python
# Test targets
targets = [
    {"target": "universal", "url": "https://example.com"},
    {"target": "web", "url": "https://example.com"},
    {"target": "amazon_search", "query": "book", "domain": "com"},
]

for test in targets:
    print(f"Testing: {test}")
    response = requests.post(
        "https://scraper-api.decodo.com/v2/scrape",
        json=test,
        headers=headers
    )
    print(f"  Result: {response.status_code}")
    print()
```

---

### Step 5: Check for Account Separation 🔀

**Hypothesis**: Core and Advanced might be separate accounts/credentials

**Test**:
1. Check if you have different usernames for each plan
2. Look in `.env` for multiple credential sets
3. Check email for separate account confirmation emails

**Possible scenarios**:
- Scenario A: Same account, different plans (most common)
- Scenario B: Two separate accounts with different credentials
- Scenario C: Plans require different API endpoints

---

### Step 6: Contact Decodo Support 📧

If above steps don't resolve, contact support with these details:

**Email**: support@decodo.com (or check dashboard for support link)

**Information to provide**:
```
Subject: 429 Rate Limit Error - Account U0000319432

Hi Decodo Support,

I'm experiencing 429 rate limit errors when trying to use my Decodo account.

Account Details:
- Username: U0000319432
- Plans: Core (90K credits) + Advanced (4.5K remaining)
- Endpoint: https://scraper-api.decodo.com/v2/scrape
- Target: universal
- Error: "Your request couldn't be processed due to rate limits"

Questions:
1. Can you confirm my current credit balance for both plans?
2. Are my credentials correct for accessing Core plan features?
3. Is there a separate credential or endpoint for Core vs Advanced?
4. Is my subscription active and not expired?

Test request that fails:
[Include curl command or code snippet]

Error response:
[Include full error message]

Thanks for your help!
```

---

### Step 7: Wait for Rate Limit Reset ⏰

**If rate limits are temporary**:
- Standard reset time: Usually 1 minute for req/s limits
- Daily limits: Reset at midnight UTC
- Check `RateLimit-Reset` header for exact time

**Test after waiting**:
```bash
# Wait 5 minutes, then retry
sleep 300
python3 shared/abebooks_scraper.py
```

---

## Common Issues & Solutions

### Issue 1: "Used all requests"

**Cause**: Credit balance depleted
**Solution**:
- Check dashboard for actual balance
- Purchase more credits if needed
- Verify which plan you're hitting

### Issue 2: "Subscription period has ended"

**Cause**: Plan expired
**Solution**:
- Renew subscription in dashboard
- Check expiration dates
- Update payment method if needed

### Issue 3: "Exceeded req/s rate"

**Cause**: Making requests too fast
**Solution**:
```python
# Reduce rate limit in client
client = DecodoClient(
    username=username,
    password=password,
    rate_limit=1  # 1 req/sec instead of 30
)
```

### Issue 4: Wrong API Endpoint

**Cause**: Core plan might use different endpoint
**Solution**:
- Try `https://api.decodo.com` instead of `https://scraper-api.decodo.com`
- Check documentation for Core plan specific endpoints
- Ask support for correct endpoint

---

## Temporary Workarounds

### While debugging Decodo, use these alternatives:

#### 1. Amazon Data → Use PA-API (Free)
```bash
# Set up Amazon Product Advertising API
# Free alternative to Decodo for Amazon
```

#### 2. eBay Data → Use Finding API (Free)
```bash
# Set up eBay Finding API
# Free alternative to Decodo for eBay sold comps
```

#### 3. Manual Collection
```bash
# Temporarily collect critical ISBNs manually
# Use browser + copy/paste for high-value books
```

#### 4. Batch Collection Later
```bash
# Queue ISBNs to collect once Decodo is working
# Save list to file for bulk processing
```

---

## Testing Checklist

Before attempting full collection:

- [ ] Verified account status in dashboard
- [ ] Confirmed credit balance (Core: ~90K, Advanced: ~4.5K)
- [ ] Tested credentials with simple request
- [ ] Checked rate limit headers
- [ ] Tested different targets (universal, web, etc.)
- [ ] Waited for rate limit reset (5+ minutes)
- [ ] Reduced rate_limit to 1 req/sec in client
- [ ] Confirmed subscription is active
- [ ] No warnings/notices in dashboard
- [ ] Can successfully scrape example.com

**Only proceed with AbeBooks collection after all checks pass ✅**

---

## Next Steps After Resolution

1. **Test with 10 ISBNs** - Verify everything works
2. **Run 100 ISBN test** - Ensure stability
3. **Monitor credit usage** - Track consumption rate
4. **Scale to full collection** - Run bulk script

---

## Prevention

### To avoid future issues:

1. **Monitor credit usage**: Check dashboard weekly
2. **Set usage alerts**: If available in dashboard
3. **Conservative rate limits**: Use 1-2 req/sec, not 30
4. **Batch saves**: Save results frequently during collection
5. **Resume capability**: Always use `--resume` flag
6. **Plan ahead**: Don't use last 10% of credits without buffer

---

## Support Resources

- **Dashboard**: https://dashboard.decodo.com
- **Documentation**: https://help.decodo.com
- **Support Email**: support@decodo.com (verify in dashboard)
- **Status Page**: Check if Decodo has a status page for outages

---

## Decision Tree

```
Getting 429 errors?
├─ Check dashboard
│  ├─ Credits = 0? → Purchase more credits
│  ├─ Expired? → Renew subscription
│  └─ Active with credits? → Continue below
├─ Wait 5 minutes → Retry
│  ├─ Works? → Rate limit issue, reduce speed
│  └─ Still fails? → Continue below
├─ Test with example.com
│  ├─ Works? → Target-specific issue (AbeBooks blocking)
│  └─ Fails? → Account/credential issue
└─ Contact support with details
```

---

## Current Status Summary

**Before troubleshooting**:
- ❌ Getting 429 errors on all requests
- ❓ Unclear if Core plan is accessible
- ❓ Unknown actual credit balance
- ⚠️  Using Advanced credits for Amazon (expensive)

**After troubleshooting**:
- ✅ Account status verified
- ✅ Correct credentials confirmed
- ✅ Core plan accessible
- ✅ Credit balance known
- ✅ Rate limits understood
- ✅ Ready for AbeBooks collection

**Goal**: Get to "After troubleshooting" state ASAP so we can use those 90K Core credits effectively!
