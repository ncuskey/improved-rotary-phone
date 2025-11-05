#!/usr/bin/env python3
"""
Generate PDF report with vendor feature pattern analysis and visualizations.
"""
import json
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.backends.backend_pdf import PdfPages
from pathlib import Path
import numpy as np
from datetime import datetime

def load_vendor_metadata():
    """Load metadata from all vendor models."""
    model_dir = Path('isbn_lot_optimizer/models/stacking')
    vendors = ['ebay', 'abebooks', 'amazon', 'biblio', 'alibris', 'zvab']

    feature_importances = {}
    model_stats = {}

    for vendor in vendors:
        metadata_path = model_dir / f'{vendor}_metadata.json'
        if metadata_path.exists():
            with open(metadata_path) as f:
                data = json.load(f)
                feature_importances[vendor] = data.get('feature_importance', {})
                model_stats[vendor] = {
                    'test_mae': data.get('test_mae'),
                    'test_r2': data.get('test_r2'),
                    'test_rmse': data.get('test_rmse'),
                    'train_mae': data.get('train_mae'),
                    'n_samples': data.get('n_samples'),
                    'n_features': data.get('n_features')
                }

    return feature_importances, model_stats


def create_title_page(fig):
    """Create title page for the report."""
    ax = fig.add_subplot(111)
    ax.axis('off')

    # Title
    ax.text(0.5, 0.7, 'Vendor Feature Pattern Analysis',
            ha='center', va='center', fontsize=28, fontweight='bold')

    # Subtitle
    ax.text(0.5, 0.6, 'ML Model Feature Importance Across 6 Marketplaces',
            ha='center', va='center', fontsize=16, style='italic')

    # Date
    ax.text(0.5, 0.45, f'Generated: {datetime.now().strftime("%B %d, %Y")}',
            ha='center', va='center', fontsize=12)

    # Summary box
    summary_text = """
    This report analyzes feature importance patterns across 6 vendor-specific
    ML models (eBay, AbeBooks, Amazon, Biblio, Alibris, Zvab) to identify:

    • Which features are universally important vs vendor-specific
    • Whether premiums (signed, first edition) are consistent across markets
    • BookFinder feature impact by vendor
    • Why signed/first edition features show low importance
    """

    ax.text(0.5, 0.25, summary_text,
            ha='center', va='center', fontsize=11,
            bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.3))

    # Footer
    ax.text(0.5, 0.05, 'ISBN Lot Optimizer ML Analysis',
            ha='center', va='center', fontsize=10, style='italic', color='gray')


def plot_model_performance(model_stats):
    """Create bar chart comparing model performance."""
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 6))

    vendors = ['ebay', 'abebooks', 'amazon', 'biblio', 'alibris', 'zvab']
    vendor_labels = [v.title() for v in vendors]

    # Test MAE comparison
    test_maes = [model_stats.get(v, {}).get('test_mae', 0) for v in vendors]
    colors = ['#1f77b4', '#2ca02c', '#ff7f0e', '#9467bd', '#8c564b', '#e377c2']

    bars1 = ax1.bar(vendor_labels, test_maes, color=colors, alpha=0.7, edgecolor='black')
    ax1.set_ylabel('Test MAE ($)', fontsize=12, fontweight='bold')
    ax1.set_title('Model Performance: Test MAE by Vendor', fontsize=14, fontweight='bold')
    ax1.set_ylim(0, max(test_maes) * 1.15)
    ax1.grid(axis='y', alpha=0.3, linestyle='--')

    # Add value labels on bars
    for bar, mae in zip(bars1, test_maes):
        height = bar.get_height()
        ax1.text(bar.get_x() + bar.get_width()/2., height,
                f'${mae:.2f}', ha='center', va='bottom', fontsize=10, fontweight='bold')

    # R² comparison
    test_r2s = [model_stats.get(v, {}).get('test_r2', 0) for v in vendors]
    bars2 = ax2.bar(vendor_labels, test_r2s, color=colors, alpha=0.7, edgecolor='black')
    ax2.set_ylabel('Test R² Score', fontsize=12, fontweight='bold')
    ax2.set_title('Model Performance: R² by Vendor', fontsize=14, fontweight='bold')
    ax2.axhline(y=0, color='red', linestyle='--', linewidth=1, alpha=0.5)
    ax2.grid(axis='y', alpha=0.3, linestyle='--')

    # Add value labels
    for bar, r2 in zip(bars2, test_r2s):
        height = bar.get_height()
        va = 'bottom' if height >= 0 else 'top'
        ax2.text(bar.get_x() + bar.get_width()/2., height,
                f'{r2:.3f}', ha='center', va=va, fontsize=10, fontweight='bold')

    plt.tight_layout()
    return fig


def plot_universal_features(feature_importances):
    """Heatmap of universal features across vendors."""
    fig, ax = plt.subplots(figsize=(14, 8))

    key_features = [
        ('page_count', 'Page Count'),
        ('age_years', 'Age (Years)'),
        ('log_ratings', 'Log(Ratings)'),
        ('rating', 'Rating'),
        ('is_signed', 'Signed'),
        ('is_first_edition', 'First Edition'),
        ('is_hardcover', 'Hardcover'),
        ('log_amazon_rank', 'Amazon Rank'),
        ('abebooks_avg_price', 'AbeBooks Price'),
        ('is_fiction', 'Fiction'),
    ]

    vendors = ['ebay', 'abebooks', 'amazon', 'biblio', 'alibris', 'zvab']
    vendor_labels = [v.title() for v in vendors]

    # Build matrix
    data = []
    feature_labels = []
    for feat_key, feat_name in key_features:
        row = []
        for vendor in vendors:
            imps = feature_importances.get(vendor, {})
            importance = imps.get(feat_key, 0) * 100  # Convert to percentage
            row.append(importance)
        data.append(row)
        feature_labels.append(feat_name)

    data = np.array(data)

    # Create heatmap
    im = ax.imshow(data, cmap='YlOrRd', aspect='auto', vmin=0, vmax=35)

    # Set ticks
    ax.set_xticks(np.arange(len(vendors)))
    ax.set_yticks(np.arange(len(feature_labels)))
    ax.set_xticklabels(vendor_labels, fontsize=11, fontweight='bold')
    ax.set_yticklabels(feature_labels, fontsize=11)

    # Rotate x labels
    plt.setp(ax.get_xticklabels(), rotation=45, ha="right", rotation_mode="anchor")

    # Add text annotations
    for i in range(len(feature_labels)):
        for j in range(len(vendors)):
            value = data[i, j]
            if value > 0.1:
                text = ax.text(j, i, f'{value:.1f}%',
                             ha="center", va="center", color="black" if value < 20 else "white",
                             fontsize=9, fontweight='bold')

    # Colorbar
    cbar = plt.colorbar(im, ax=ax)
    cbar.set_label('Importance (%)', rotation=270, labelpad=20, fontsize=12, fontweight='bold')

    ax.set_title('Feature Importance Heatmap: Key Features Across Vendors',
                fontsize=14, fontweight='bold', pad=20)

    plt.tight_layout()
    return fig


def plot_bookfinder_importance(feature_importances):
    """Bar chart showing total BookFinder importance per vendor."""
    fig, ax = plt.subplots(figsize=(12, 6))

    vendors = ['ebay', 'abebooks', 'amazon', 'biblio', 'alibris', 'zvab']
    vendor_labels = [v.title() for v in vendors]

    # Calculate total BookFinder importance
    bf_totals = []
    for vendor in vendors:
        imps = feature_importances.get(vendor, {})
        total_bf = sum(imp for feat, imp in imps.items() if feat.startswith('bookfinder_'))
        bf_totals.append(total_bf * 100)  # Convert to percentage

    # Create bars with different colors for major vs specialty
    colors = ['#d62728', '#d62728', '#d62728', '#2ca02c', '#2ca02c', '#2ca02c']
    bars = ax.bar(vendor_labels, bf_totals, color=colors, alpha=0.7, edgecolor='black', linewidth=2)

    ax.set_ylabel('Total BookFinder Importance (%)', fontsize=12, fontweight='bold')
    ax.set_title('BookFinder Feature Importance by Vendor', fontsize=14, fontweight='bold')
    ax.set_ylim(0, 85)
    ax.grid(axis='y', alpha=0.3, linestyle='--')

    # Add value labels
    for bar, total in zip(bars, bf_totals):
        height = bar.get_height()
        if height > 0.1:
            ax.text(bar.get_x() + bar.get_width()/2., height,
                   f'{total:.1f}%', ha='center', va='bottom', fontsize=12, fontweight='bold')
        else:
            ax.text(bar.get_x() + bar.get_width()/2., 2,
                   '0%', ha='center', va='bottom', fontsize=12, fontweight='bold')

    # Legend
    red_patch = mpatches.Patch(color='#d62728', alpha=0.7, label='Major Platforms (0%)')
    green_patch = mpatches.Patch(color='#2ca02c', alpha=0.7, label='Specialty Vendors (50-76%)')
    ax.legend(handles=[red_patch, green_patch], loc='upper left', fontsize=11)

    # Add annotation
    ax.text(0.98, 0.5, 'Specialty vendors rely\nheavily on cross-market\nBookFinder signals',
           transform=ax.transAxes, ha='right', va='center',
           fontsize=10, style='italic',
           bbox=dict(boxstyle='round', facecolor='yellow', alpha=0.3))

    plt.tight_layout()
    return fig


def plot_top_features_comparison(feature_importances):
    """Horizontal bar chart showing top 5 features for each vendor."""
    vendors = ['ebay', 'abebooks', 'amazon', 'biblio', 'alibris', 'zvab']

    fig, axes = plt.subplots(2, 3, figsize=(16, 10))
    axes = axes.flatten()

    for idx, vendor in enumerate(vendors):
        ax = axes[idx]
        imps = feature_importances.get(vendor, {})

        # Get top 5 features
        sorted_imps = sorted(imps.items(), key=lambda x: x[1], reverse=True)[:5]
        features = [f[0].replace('_', ' ').title() for f in sorted_imps]
        importances = [f[1] * 100 for f in sorted_imps]

        # Create horizontal bars
        y_pos = np.arange(len(features))
        colors_gradient = plt.cm.Blues(np.linspace(0.5, 0.9, len(features)))

        bars = ax.barh(y_pos, importances, color=colors_gradient, edgecolor='black')
        ax.set_yticks(y_pos)
        ax.set_yticklabels(features, fontsize=9)
        ax.invert_yaxis()
        ax.set_xlabel('Importance (%)', fontsize=10, fontweight='bold')
        ax.set_title(vendor.upper(), fontsize=12, fontweight='bold')
        ax.grid(axis='x', alpha=0.3, linestyle='--')

        # Add value labels
        for bar, imp in zip(bars, importances):
            width = bar.get_width()
            ax.text(width, bar.get_y() + bar.get_height()/2.,
                   f'{imp:.1f}%', ha='left', va='center', fontsize=9, fontweight='bold')

    plt.suptitle('Top 5 Features by Vendor', fontsize=16, fontweight='bold', y=0.995)
    plt.tight_layout()
    return fig


def plot_signed_first_edition_analysis():
    """Visualization of signed/first edition feature importance."""
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 6))

    # Unified model data
    features = [
        'is_signed',
        'is_first_edition',
        'bookfinder_signed_count',
        'bookfinder_signed_lowest',
        'bookfinder_first_edition_count',
        'bookfinder_first_ed_lowest'
    ]

    importances = [0.13, 0.01, 0.0, 0.61, 0.07, 0.72]  # From unified model
    colors = ['#ff7f0e', '#ff7f0e', '#1f77b4', '#1f77b4', '#1f77b4', '#1f77b4']

    # Bar chart
    y_pos = np.arange(len(features))
    bars = ax1.barh(y_pos, importances, color=colors, alpha=0.7, edgecolor='black')
    ax1.set_yticks(y_pos)
    ax1.set_yticklabels([f.replace('_', ' ').replace('bookfinder ', 'BF: ').title()
                         for f in features], fontsize=10)
    ax1.invert_yaxis()
    ax1.set_xlabel('Importance (%)', fontsize=11, fontweight='bold')
    ax1.set_title('Signed/First Edition Features\n(Unified Model)',
                 fontsize=13, fontweight='bold')
    ax1.grid(axis='x', alpha=0.3, linestyle='--')

    # Add value labels
    for bar, imp in zip(bars, importances):
        width = bar.get_width()
        if width > 0.05:
            ax1.text(width, bar.get_y() + bar.get_height()/2.,
                    f'{imp:.2f}%', ha='left', va='center', fontsize=9, fontweight='bold')
        else:
            ax1.text(0.05, bar.get_y() + bar.get_height()/2.,
                    f'{imp:.2f}%', ha='left', va='center', fontsize=9)

    # Legend
    orange_patch = mpatches.Patch(color='#ff7f0e', alpha=0.7, label='Direct Metadata')
    blue_patch = mpatches.Patch(color='#1f77b4', alpha=0.7, label='BookFinder Aggregated')
    ax1.legend(handles=[orange_patch, blue_patch], loc='lower right', fontsize=10)

    # Vendor comparison for first_edition_count
    vendors = ['Biblio', 'Alibris', 'Zvab']
    first_ed_importance = [3.19, 7.81, 0.14]

    bars2 = ax2.bar(vendors, first_ed_importance,
                   color=['#9467bd', '#8c564b', '#e377c2'],
                   alpha=0.7, edgecolor='black', linewidth=2)
    ax2.set_ylabel('Importance (%)', fontsize=11, fontweight='bold')
    ax2.set_title('BookFinder First Edition Count\n(Vendor Models)',
                 fontsize=13, fontweight='bold')
    ax2.grid(axis='y', alpha=0.3, linestyle='--')

    # Add value labels
    for bar, imp in zip(bars2, first_ed_importance):
        height = bar.get_height()
        ax2.text(bar.get_x() + bar.get_width()/2., height,
                f'{imp:.2f}%', ha='center', va='bottom', fontsize=11, fontweight='bold')

    # Add annotation
    ax2.text(0.5, 0.85, 'Higher importance when\nBookFinder coverage is better',
            transform=ax2.transAxes, ha='center', va='center',
            fontsize=10, style='italic',
            bbox=dict(boxstyle='round', facecolor='lightgreen', alpha=0.3))

    plt.tight_layout()
    return fig


def create_summary_page(feature_importances, model_stats):
    """Create summary findings page."""
    fig = plt.figure(figsize=(11, 8.5))
    ax = fig.add_subplot(111)
    ax.axis('off')

    summary_text = """
KEY FINDINGS: Vendor Feature Pattern Analysis

1. NO CONSISTENT PRICING RATIOS ACROSS VENDORS
   Each marketplace values features very differently:
   • eBay: Popularity-driven (log_ratings 31.5% importance)
   • Amazon: Size matters (page_count 30.9%, amazon_rank 22.4%)
   • AbeBooks: Self-referential (uses own pricing, 45-54% importance)
   • Specialty vendors: BookFinder-driven (50-76% total importance)

2. BOOKFINDER'S SPLIT PERSONALITY
   • Major platforms (eBay, Amazon, AbeBooks): 0% BookFinder importance
   • Specialty vendors (Biblio, Alibris, Zvab): 50-76% BookFinder importance

   Why? Major platforms have deep internal data; specialty vendors need
   external signals to price rare/collectible books.

3. SIGNED & FIRST EDITION PREMIUMS ARE INDIRECT
   Direct metadata features (is_signed, is_first_edition): ~0% importance

   Root causes:
   • Metadata rarely populated in source data
   • BookFinder coverage sparse (~5% of training samples)
   • Premiums captured indirectly through BookFinder aggregation:
     - bookfinder_signed_lowest: 0.61% importance
     - bookfinder_first_ed_lowest: 0.72% importance

   Expected: As BookFinder scraping completes (→19K ISBNs), these features
   should gain significant importance.

4. MODEL PERFORMANCE VARIES DRAMATICALLY
   • Best: AbeBooks ($0.28 MAE, R² 0.863) - exceptional
   • Worst: Amazon ($17.27 MAE, R² -0.008) - needs investigation
   • Unified model ($3.59 MAE) outperforms stacking ($5.26 MAE)

5. UNIVERSAL FEATURES SHOW MASSIVE VARIANCE
   Even features used by all 6 vendors have 0-31% importance range:
   • log_ratings: 0.0% (AbeBooks) to 31.5% (eBay)
   • page_count: 0.0% (AbeBooks) to 30.9% (Amazon)

   Conclusion: No universal pricing formulas exist.
    """

    ax.text(0.5, 0.95, 'Executive Summary',
           ha='center', va='top', fontsize=18, fontweight='bold')

    ax.text(0.05, 0.88, summary_text,
           ha='left', va='top', fontsize=9, family='monospace',
           bbox=dict(boxstyle='round', facecolor='lightblue', alpha=0.2))

    # Footer with recommendations
    footer_text = """
RECOMMENDATIONS:
✓ Continue BookFinder scraping to increase feature coverage
✓ Retrain unified model when BookFinder > 1,000 ISBNs (target: MAE < $3.00)
✓ Investigate why Amazon model performs poorly
✓ Study why AbeBooks model performs exceptionally well
    """

    ax.text(0.5, 0.08, footer_text,
           ha='center', va='top', fontsize=10,
           bbox=dict(boxstyle='round', facecolor='lightgreen', alpha=0.3))


def main():
    """Generate PDF report."""
    print("Loading vendor metadata...")
    feature_importances, model_stats = load_vendor_metadata()

    output_path = Path('docs/analysis/Vendor_Feature_Patterns.pdf')
    output_path.parent.mkdir(parents=True, exist_ok=True)

    print(f"Generating PDF report: {output_path}")

    with PdfPages(output_path) as pdf:
        # Title page
        print("  Creating title page...")
        fig = plt.figure(figsize=(11, 8.5))
        create_title_page(fig)
        pdf.savefig(fig, bbox_inches='tight')
        plt.close()

        # Model performance
        print("  Plotting model performance...")
        fig = plot_model_performance(model_stats)
        pdf.savefig(fig, bbox_inches='tight')
        plt.close()

        # Universal features heatmap
        print("  Creating feature importance heatmap...")
        fig = plot_universal_features(feature_importances)
        pdf.savefig(fig, bbox_inches='tight')
        plt.close()

        # BookFinder importance
        print("  Plotting BookFinder importance...")
        fig = plot_bookfinder_importance(feature_importances)
        pdf.savefig(fig, bbox_inches='tight')
        plt.close()

        # Top features by vendor
        print("  Creating top features comparison...")
        fig = plot_top_features_comparison(feature_importances)
        pdf.savefig(fig, bbox_inches='tight')
        plt.close()

        # Signed/First edition analysis
        print("  Analyzing signed/first edition features...")
        fig = plot_signed_first_edition_analysis()
        pdf.savefig(fig, bbox_inches='tight')
        plt.close()

        # Summary page
        print("  Creating summary page...")
        fig = plt.figure(figsize=(11, 8.5))
        create_summary_page(feature_importances, model_stats)
        pdf.savefig(fig, bbox_inches='tight')
        plt.close()

        # PDF metadata
        d = pdf.infodict()
        d['Title'] = 'Vendor Feature Pattern Analysis'
        d['Author'] = 'ISBN Lot Optimizer ML System'
        d['Subject'] = 'Feature Importance Analysis Across 6 Book Vendor Models'
        d['Keywords'] = 'Machine Learning, Feature Importance, Vendor Analysis'
        d['CreationDate'] = datetime.now()

    print(f"\n✓ PDF report generated successfully: {output_path}")
    print(f"  File size: {output_path.stat().st_size / 1024:.1f} KB")
    print(f"  Pages: 7")


if __name__ == "__main__":
    main()
