
================================================================================
CROSS-PLATFORM PRICE SCALING ANALYSIS
Generated: 2025-11-01 10:35:27
================================================================================

Analyzing 748 books with both eBay and AbeBooks data...

================================================================================
PLATFORM SCALING FACTOR ANALYSIS
================================================================================

Overall Scaling Factors (n=748):
  eBay → AbeBooks min:
    Mean ratio:   6.07x
    Median ratio: 5.75x
    Std dev:      3.10
    Min/Max:      0.03x / 15.05x

  eBay → AbeBooks avg:
    Mean ratio:   1.65x
    Median ratio: 1.71x
    Std dev:      0.83
    Min/Max:      0.01x / 4.44x

================================================================================
SCALING FACTORS BY CONDITION
================================================================================

Good            (n=635): Mean= 6.04x  Median= 5.75x  StdDev=3.13
Very Good       (n=113): Mean= 6.26x  Median= 5.75x  StdDev=2.96

================================================================================
SCALING FACTORS BY BINDING
================================================================================

Hardcover            (n= 92): Mean= 6.12x  Median= 5.76x  StdDev=2.84
Mass Market Paperback (n=  4): Mean= 5.67x  Median= 5.33x  StdDev=2.79
Paperback            (n= 28): Mean= 6.38x  Median= 5.69x  StdDev=3.11
Unknown              (n=622): Mean= 6.05x  Median= 5.75x  StdDev=3.15

================================================================================
SCALING FACTORS BY ABEBOOKS PRICE TIER
================================================================================

Ultra-cheap ($0-2)        (n=406): Mean= 8.25x  Median= 8.33x  StdDev=2.30
Budget ($2-5)             (n=293): Mean= 3.87x  Median= 3.82x  StdDev=1.29
Mid-tier ($5-10)          (n= 32): Mean= 1.47x  Median= 1.47x  StdDev=0.42
Premium ($10-20)          (n=  9): Mean= 0.80x  Median= 0.89x  StdDev=0.31
High-end ($20+)           (n=  8): Mean= 0.26x  Median= 0.22x  StdDev=0.21

================================================================================
SCALING FACTORS BY ABEBOOKS SELLER COUNT
================================================================================

Low (1-20 sellers)             (n= 16): Mean= 1.22x  Median= 0.96x  StdDev=1.15
Medium (21-60 sellers)         (n= 44): Mean= 3.32x  Median= 2.50x  StdDev=2.49
High (61-100 sellers)          (n=666): Mean= 6.37x  Median= 6.03x  StdDev=2.98
Very high (100+ sellers)       (n= 26): Mean= 6.58x  Median= 5.51x  StdDev=3.37

================================================================================
SCALING FACTORS BY SPECIAL FEATURES
================================================================================

Signed books: 1 (insufficient for comparison)
Unsigned books: 747

First Edition (n= 66):    Mean= 6.37x  Median= 5.88x  StdDev=2.91
Not First (n=682):       Mean= 6.04x  Median= 5.74x  StdDev=3.12

================================================================================
PREDICTION ACCURACY TESTING
================================================================================

Mean scaling (6.18x)     :
  MAE:  $10.86
  RMSE: $48.64
  Bias: $+7.58 (overestimation)
  Within 20%: 22.1%
  Within 50%: 67.8%

Median scaling (5.00x)   :
  MAE:  $10.31
  RMSE: $46.03
  Bias: $+6.61 (overestimation)
  Within 20%: 22.7%
  Within 50%: 67.5%

Conservative (3.00x)     :
  MAE:  $7.71
  RMSE: $24.05
  Bias: $-1.82 (underestimation)
  Within 20%: 15.4%
  Within 50%: 44.3%

Moderate (4.00x)         :
  MAE:  $8.14
  RMSE: $31.83
  Bias: $+1.24 (overestimation)
  Within 20%: 19.7%
  Within 50%: 54.0%

Use AbeBooks avg (1.9x)  :
  MAE:  $12.38
  RMSE: $56.34
  Bias: $+10.16 (overestimation)
  Within 20%: 32.2%
  Within 50%: 64.0%


================================================================================
RECOMMENDED ML FEATURES FOR CROSS-PLATFORM SCALING
================================================================================

1. PLATFORM RATIO FEATURES:
   - ebay_abebooks_min_ratio = estimated_price / abebooks_min_price
   - ebay_abebooks_avg_ratio = estimated_price / abebooks_avg_price
   - Helps model learn platform premiums

2. SCALED PRICE FEATURES:
   - abebooks_scaled_to_ebay = abebooks_min_price * 5.0  # Use median
   - abebooks_premium = estimated_price - abebooks_scaled_to_ebay
   - Helps model see collectibility signal

3. MARKET SEGMENT FEATURES:
   - is_collectible_market = (ebay_abebooks_min_ratio > 2.0)
   - is_commodity_market = (0.8 <= ebay_abebooks_min_ratio <= 1.2)
   - collectibility_score = ebay_abebooks_min_ratio / 2.0  # Normalized

4. COMPETITION-ADJUSTED SCALING:
   - High competition (60+ sellers): Scale by 3.5x
   - Medium competition (20-60): Scale by 5.0x
   - Low competition (1-20): Scale by 7.5x
   - abebooks_competitive_estimate = abebooks_min * competition_scale

5. PRICE TIER SCALING:
   - Ultra-cheap ($0-2): Scale by 8.5x (highest premium)
   - Budget ($2-5): Scale by 5.5x
   - Mid-tier ($5-10): Scale by 3.0x
   - Premium ($10+): Scale by 1.5x (prices converge)

6. FALLBACK ESTIMATION:
   - When eBay data missing: Use abebooks_avg_price * 2.0
   - When AbeBooks missing: Use ebay_price / 5.0 for floor estimate


================================================================================
ADAPTIVE SCALING PERFORMANCE
================================================================================

Competition-aware scaling (3.5x-7.5x based on seller count):
  Predictions within 20%: 17.6%
  Predictions within 50%: 49.7%


================================================================================
SCALING OUTLIERS (Where Simple Ratios Fail)
================================================================================

Top 20 books where 5.0x scaling fails (>50% error):

 Error | Expected |  Actual | AbeBooks | Title                                        
----------------------------------------------------------------------------------------------------
17545.9% | $ 749.95 | $  4.25 | $ 149.99 | Sun Valley                                   
6702.4% | $ 542.15 | $  7.97 | $ 108.43 | Sea Level                                    
4237.1% | $ 444.55 | $ 10.25 | $  88.91 | An Introduction to Computers for Paralegals  
2463.5% | $ 108.95 | $  4.25 | $  21.79 | The Natural World                            
1947.1% | $ 200.00 | $  9.77 | $  40.00 | Splinter of the Mind's Eye                   
1402.5% | $  90.15 | $  6.00 | $  18.03 | A Chinese Life                               
1346.8% | $ 148.30 | $ 10.25 | $  29.66 | Hello Neighbor Collection                    
1233.3% | $  80.00 | $  6.00 | $  16.00 | On Someone Else's Nickel                     
1040.0% | $  48.45 | $  4.25 | $   9.69 | J.R. Simplot                                 
882.9% | $ 117.95 | $ 12.00 | $  23.59 | Campbell Biology                             
870.8% | $  58.25 | $  6.00 | $  11.65 | The Fireman                                  
724.3% | $ 106.75 | $ 12.95 | $  21.35 | 2666                                         
644.7% | $  31.65 | $  4.25 | $   6.33 | The Elementary Particles                     
555.8% | $  39.35 | $  6.00 | $   7.87 | The Tiger                                    
470.7% | $  39.95 | $  7.00 | $   7.99 | Long Shadows                                 
468.2% | $  55.40 | $  9.75 | $  11.08 | The Right to Remain Silent                   
461.9% | $  56.70 | $ 10.09 | $  11.34 | The Last of All Possible Worlds              
428.2% | $  22.45 | $  4.25 | $   4.49 | The First Stone                              
425.9% | $  53.90 | $ 10.25 | $  10.78 | Six Contemporary Chinese Women Writers IV.   
420.4% | $  68.95 | $ 13.25 | $  13.79 | All Adults Here                              

Total outliers (>50% error): 262 out of 748 (35.0%)

================================================================================
ANALYSIS COMPLETE
================================================================================

