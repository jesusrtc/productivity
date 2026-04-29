"""Generate registration spike visualizations from real Trino data."""

import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import numpy as np
from datetime import datetime

OUT = '/Users/jcortes/projects/investigation-registration/assets'

# ── Real data from Trino queries ──

dates = [datetime(2026, 3, 24) + __import__('datetime').timedelta(days=i) for i in range(15)]

# Edge/138 daily regs (03/24 - 04/07)
edge_138 = [31, 37, 44, 38, 36, 35, 54, 38, 48, 47, 24, 17, 13, 50, 671]
# Edge/139 daily regs (03/24 - 04/07)
edge_139 = [25, 25, 18, 41, 15, 17, 30, 41, 24, 28, 20, 9, 11, 33, 515]
# Combined
combined = [a + b for a, b in zip(edge_138, edge_139)]

# ── Plot 1: IOC UA spike (two panels) ──

fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 8), sharex=True)
fig.suptitle('Registration Spike: IOC User-Agents (2026-04-07)', fontsize=14, fontweight='bold')

baseline_138 = edge_138[:-1]
mean_138 = np.mean(baseline_138)
ax1.plot(dates, edge_138, 'o-', color='#0077B5', linewidth=2, markersize=6, label='Daily Registrations')
ax1.axhline(y=mean_138, color='gray', linestyle='--', alpha=0.7, label=f'Baseline Mean ({mean_138:.0f})')
ax1.axhline(y=mean_138 + 2*np.std(baseline_138), color='red', linestyle=':', alpha=0.7,
            label=f'+2\u03c3 ({mean_138 + 2*np.std(baseline_138):.0f})')
ax1.annotate(f'671 regs\n(~{671/mean_138:.0f}x baseline)', xy=(dates[-1], 671), xytext=(dates[-4], 550),
             arrowprops=dict(arrowstyle='->', color='red', lw=2), fontsize=11, color='red', fontweight='bold')
ax1.set_ylabel('Registrations')
ax1.set_title('Edge/138.0.0.0 (Chrome/138)', fontsize=11)
ax1.legend(loc='upper left', fontsize=9)
ax1.set_ylim(0, 750)
ax1.grid(True, alpha=0.3)

baseline_139 = edge_139[:-1]
mean_139 = np.mean(baseline_139)
ax2.plot(dates, edge_139, 'o-', color='#00A0DC', linewidth=2, markersize=6, label='Daily Registrations')
ax2.axhline(y=mean_139, color='gray', linestyle='--', alpha=0.7, label=f'Baseline Mean ({mean_139:.0f})')
ax2.axhline(y=mean_139 + 2*np.std(baseline_139), color='red', linestyle=':', alpha=0.7,
            label=f'+2\u03c3 ({mean_139 + 2*np.std(baseline_139):.0f})')
ax2.annotate(f'515 regs\n(~{515/mean_139:.0f}x baseline)', xy=(dates[-1], 515), xytext=(dates[-4], 420),
             arrowprops=dict(arrowstyle='->', color='red', lw=2), fontsize=11, color='red', fontweight='bold')
ax2.set_ylabel('Registrations')
ax2.set_title('Edge/139.0.0.0 (Chrome/139)', fontsize=11)
ax2.legend(loc='upper left', fontsize=9)
ax2.set_ylim(0, 600)
ax2.grid(True, alpha=0.3)

ax2.xaxis.set_major_formatter(mdates.DateFormatter('%m/%d'))
plt.xticks(dates, rotation=45)
ax2.set_xlabel('Date (2026)')
plt.tight_layout()
plt.savefig(f'{OUT}/reg_spike_by_useragent.png', dpi=150, bbox_inches='tight')
print('Saved reg_spike_by_useragent.png')

# ── Plot 2: Hourly distribution on spike day ──

hours = list(range(24))
# Edge/138 hourly regs on 04/07 (from Trino)
h138 = [42, 21, 25, 11, 26, 17, 29, 32, 41, 26, 14, 35, 15, 0, 1, 1, 0, 64, 73, 74, 65, 16, 31, 12]
# Edge/139 hourly regs on 04/07
h139 = [13, 38, 3, 44, 17, 10, 36, 31, 18, 23, 38, 10, 21, 6, 0, 1, 1, 72, 18, 10, 11, 41, 30, 23]

fig2, ax3 = plt.subplots(figsize=(12, 5))
bar_width = 0.4
x = np.arange(24)
ax3.bar(x - bar_width/2, h138, bar_width, color='#0077B5', label='Edge/138', alpha=0.85)
ax3.bar(x + bar_width/2, h139, bar_width, color='#00A0DC', label='Edge/139', alpha=0.85)
ax3.set_xlabel('Hour (UTC)')
ax3.set_ylabel('Registrations')
ax3.set_title('Hourly Registration Pattern on Spike Day (2026-04-07 UTC)', fontsize=13, fontweight='bold')
ax3.set_xticks(hours)
ax3.legend()
ax3.grid(True, alpha=0.3, axis='y')

# Annotate the two burst windows
ax3.axvspan(0, 12.5, alpha=0.05, color='red')
ax3.axvspan(16.5, 23.5, alpha=0.05, color='red')
ax3.text(6, max(max(h138), max(h139)) * 0.95, 'Burst 1', ha='center', fontsize=10, color='red', fontstyle='italic')
ax3.text(20, max(max(h138), max(h139)) * 0.95, 'Burst 2', ha='center', fontsize=10, color='red', fontstyle='italic')

plt.tight_layout()
plt.savefig(f'{OUT}/hourly_pattern_spike_day.png', dpi=150, bbox_inches='tight')
print('Saved hourly_pattern_spike_day.png')

# ── Plot 3: Geo distribution (top 10 countries) ──

countries = ['Brazil', 'USA', 'Mexico', 'Russia', 'Peru', 'Colombia', 'Canada', 'Ukraine', 'Italy', 'UK']
counts = [173, 171, 164, 87, 63, 43, 36, 33, 28, 23]

fig3, ax4 = plt.subplots(figsize=(10, 5))
bars = ax4.barh(countries[::-1], counts[::-1], color='#0077B5', alpha=0.85)
ax4.set_xlabel('Registrations')
ax4.set_title('Geographic Distribution of IOC Registrations (2026-04-07)', fontsize=13, fontweight='bold')
ax4.grid(True, alpha=0.3, axis='x')
for bar, count in zip(bars, counts[::-1]):
    ax4.text(bar.get_width() + 2, bar.get_y() + bar.get_height()/2, str(count), va='center', fontsize=10)
plt.tight_layout()
plt.savefig(f'{OUT}/geo_distribution.png', dpi=150, bbox_inches='tight')
print('Saved geo_distribution.png')

print('\nAll plots generated.')
