"""Attribution plot: IOC cohorts vs Other registrations."""

import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import numpy as np
from datetime import datetime, timedelta

OUT = '/Users/jcortes/projects/investigation-registration/assets'

dates = [datetime(2026, 3, 24) + timedelta(days=i) for i in range(15)]

# From Trino: CASE WHEN IOC Edge 138/139, auto-gen Gmail (long prefix), Other
edge_ua  = [56, 62, 62, 79, 51, 52, 84, 79, 72, 75, 44, 26, 24, 83, 1186]
gmail_re = [121, 188, 601, 2608, 2613, 2936, 2377, 2986, 3542, 2658, 4508, 5360, 7137, 10526, 12505]
other    = [804918, 827502, 830334, 794846, 742742, 781887, 871000, 872781, 850776, 679337, 694666, 701629, 722669, 874947, 779190]

fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(13, 9), gridspec_kw={'height_ratios': [1, 2]})
fig.suptitle('Registration Attribution: IOC Cohorts vs Other', fontsize=14, fontweight='bold')

# ── Top panel: full volume (stacked area) ──
ax1.stackplot(dates,
              other, gmail_re, edge_ua,
              labels=['Other', 'Auto-gen Gmail (regex)', 'Edge 138/139 UA'],
              colors=['#E0E0E0', '#FF6B35', '#D32F2F'], alpha=0.85)
ax1.set_ylabel('Total Registrations')
ax1.legend(loc='upper left', fontsize=9)
ax1.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f'{x/1e6:.1f}M' if x >= 1e6 else f'{x/1e3:.0f}K'))
ax1.grid(True, alpha=0.3)
ax1.set_title('Full Registration Volume (IOC share is tiny at this scale)', fontsize=10)
ax1.xaxis.set_major_formatter(mdates.DateFormatter('%m/%d'))

# ── Bottom panel: zoomed into IOC cohorts only ──
ax2.fill_between(dates, 0, gmail_re, alpha=0.4, color='#FF6B35', label='Auto-gen Gmail: ^[a-z]{8,}0[0-9]{1,2}\\.gmail\\.com$')
ax2.plot(dates, gmail_re, 'o-', color='#FF6B35', linewidth=2, markersize=5)

ax2.fill_between(dates, 0, edge_ua, alpha=0.4, color='#D32F2F', label='Edge 138/139 UA (alert IOC)')
ax2.plot(dates, edge_ua, 's-', color='#D32F2F', linewidth=2, markersize=5)

# Annotate key points
ax2.annotate(f'12,505', xy=(dates[-1], gmail_re[-1]), xytext=(dates[-3], gmail_re[-1] + 1500),
             arrowprops=dict(arrowstyle='->', color='#FF6B35', lw=1.5), fontsize=10, color='#FF6B35', fontweight='bold')
ax2.annotate(f'1,186\n(alert)', xy=(dates[-1], edge_ua[-1]), xytext=(dates[-5], edge_ua[-1] + 2500),
             arrowprops=dict(arrowstyle='->', color='#D32F2F', lw=1.5), fontsize=10, color='#D32F2F', fontweight='bold')

# Annotate the ramp
ax2.annotate(f'Ramp starts\n(~600)', xy=(dates[2], gmail_re[2]), xytext=(dates[0], 4000),
             arrowprops=dict(arrowstyle='->', color='gray', lw=1), fontsize=9, color='gray')

ax2.set_ylabel('IOC Registrations')
ax2.set_xlabel('Date (2026)')
ax2.legend(loc='upper left', fontsize=9)
ax2.grid(True, alpha=0.3)
ax2.set_title('IOC Cohorts Only (zoomed) — Gmail pattern is 10x larger and growing', fontsize=10)
ax2.xaxis.set_major_formatter(mdates.DateFormatter('%m/%d'))
plt.xticks(dates, rotation=45)

plt.tight_layout()
plt.savefig(f'{OUT}/attribution_ioc_vs_other.png', dpi=150, bbox_inches='tight')
print('Saved attribution_ioc_vs_other.png')
