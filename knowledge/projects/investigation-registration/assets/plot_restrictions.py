"""Restriction status and time-to-restrict plots."""

import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
import numpy as np

OUT = '/Users/jcortes/projects/investigation-registration/assets'

# ── Data from Trino ──

# Bucketed summary
buckets = ['< 1 hour', '1-6 hours', '6-24 hours', 'Not Restricted']
counts  = [436, 703, 1, 45]  # pre-existing (1) grouped with <1hr
colors  = ['#2E7D32', '#66BB6A', '#FFA726', '#D32F2F']

# Detailed time-to-restrict (hours, count) — excluding outlier at 15.6h for histogram
hours = [0.1,0.2,0.3,0.4,0.5,0.6,0.7,0.8,0.9,
         1.0,1.1,1.2,1.3,1.4,1.5,1.6,1.7,1.8,1.9,
         2.0,2.1,2.2,2.3,2.4,2.5,2.6,2.7,2.8,2.9,
         3.0,3.1,3.2,3.3,3.4,3.5,3.6,3.7,3.8,3.9,
         4.0,4.1,4.2,4.3,4.4,4.5,4.6,4.7,4.8,4.9,5.0,5.1,5.2]
cnts  = [5,176,52,41,37,21,29,28,33,
         27,66,85,54,57,40,21,18,15,13,
         14,25,15,13,15,14,21,17,16,12,
         11,12,7,16,7,7,5,9,6,7,
         9,8,3,4,7,7,3,5,5,9,9,2,1]

# Expand to individual values for histogram
individual_hours = []
for h, c in zip(hours, cnts):
    individual_hours.extend([h] * c)

fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 5.5),
                                gridspec_kw={'width_ratios': [1, 2]})
fig.suptitle('Restriction Outcomes: 1,186 IOC Accounts', fontsize=14, fontweight='bold')

# ── Left: restriction status donut ──
wedges, texts, autotexts = ax1.pie(
    counts, labels=buckets, colors=colors, autopct='%1.1f%%',
    startangle=90, pctdistance=0.75, textprops={'fontsize': 10})
for t in autotexts:
    t.set_fontweight('bold')
centre_circle = plt.Circle((0, 0), 0.50, fc='white')
ax1.add_artist(centre_circle)
ax1.text(0, 0, f'96.2%\nrestricted', ha='center', va='center',
         fontsize=13, fontweight='bold', color='#2E7D32')
ax1.set_title('Restriction Status', fontsize=11)

# ── Right: time-to-restrict histogram ──
ax2.hist(individual_hours, bins=np.arange(0, 5.5, 0.2), color='#0077B5',
         edgecolor='white', alpha=0.85)
ax2.axvline(x=np.median(individual_hours), color='red', linestyle='--', linewidth=2,
            label=f'Median: {np.median(individual_hours):.1f}h')
ax2.axvline(x=np.mean(individual_hours), color='orange', linestyle='--', linewidth=2,
            label=f'Mean: {np.mean(individual_hours):.1f}h')

# Annotate the 12-minute spike
ax2.annotate(f'176 accounts\nrestricted at ~12 min',
             xy=(0.2, 176), xytext=(1.5, 170),
             arrowprops=dict(arrowstyle='->', color='red', lw=1.5),
             fontsize=10, color='red', fontweight='bold')

ax2.set_xlabel('Hours from Registration to Restriction')
ax2.set_ylabel('Number of Accounts')
ax2.set_title('Time to Restrict (restricted accounts only, N=1,141)', fontsize=11)
ax2.legend(fontsize=10)
ax2.grid(True, alpha=0.3, axis='y')
ax2.xaxis.set_major_locator(ticker.MultipleLocator(0.5))

plt.tight_layout()
plt.savefig(f'{OUT}/restriction_time_distribution.png', dpi=150, bbox_inches='tight')
print('Saved restriction_time_distribution.png')

# ── Cumulative restriction curve ──
fig2, ax3 = plt.subplots(figsize=(10, 5))
sorted_hours = sorted(individual_hours)
cumulative = np.arange(1, len(sorted_hours) + 1)
pct_cumulative = cumulative / 1186.0 * 100  # out of total 1186

ax3.plot(sorted_hours, pct_cumulative, color='#0077B5', linewidth=2.5)
ax3.axhline(y=50, color='gray', linestyle=':', alpha=0.5)
ax3.axhline(y=90, color='gray', linestyle=':', alpha=0.5)
ax3.axhline(y=96.2, color='#2E7D32', linestyle='--', alpha=0.7, label='Final: 96.2% restricted')

# Mark key percentiles
p50_idx = np.searchsorted(pct_cumulative, 50)
p90_idx = np.searchsorted(pct_cumulative, 90)
if p50_idx < len(sorted_hours):
    ax3.plot(sorted_hours[p50_idx], 50, 'ro', markersize=8)
    ax3.annotate(f'50% at {sorted_hours[p50_idx]:.1f}h',
                 xy=(sorted_hours[p50_idx], 50), xytext=(sorted_hours[p50_idx]+0.5, 45),
                 arrowprops=dict(arrowstyle='->', color='red'), fontsize=10, color='red')
if p90_idx < len(sorted_hours):
    ax3.plot(sorted_hours[p90_idx], 90, 'ro', markersize=8)
    ax3.annotate(f'90% at {sorted_hours[p90_idx]:.1f}h',
                 xy=(sorted_hours[p90_idx], 90), xytext=(sorted_hours[p90_idx]+0.5, 85),
                 arrowprops=dict(arrowstyle='->', color='red'), fontsize=10, color='red')

ax3.set_xlabel('Hours from Registration')
ax3.set_ylabel('% of IOC Accounts Restricted')
ax3.set_title('Cumulative Restriction Rate Over Time (N=1,186)', fontsize=13, fontweight='bold')
ax3.set_xlim(-0.1, 5.5)
ax3.set_ylim(0, 102)
ax3.legend(fontsize=10)
ax3.grid(True, alpha=0.3)

plt.tight_layout()
plt.savefig(f'{OUT}/cumulative_restriction_curve.png', dpi=150, bbox_inches='tight')
print('Saved cumulative_restriction_curve.png')
