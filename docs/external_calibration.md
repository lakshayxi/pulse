# External calibration boundary

Pulse uses public Indian-bank disclosures to improve the structure of its
synthetic customer lifecycle. The evidence is directional. It does not provide
a numerical benchmark for the generated D7, D30, D60, or D90 retention rates.

## What the public evidence supports

| Bank | Public evidence | Design implication |
|---|---|---|
| State Bank of India | The FY2025 analyst presentation reports 8.8 crore YONO registered users, 13.9 crore retail internet-banking customers, and separate UPI and mobile-banking footprints. | Model more than one digital state and allow the channel mix to change. |
| Axis Bank | The FY2025 integrated report reports about 3 crore registered mobile-banking customers, more than 15 million monthly active users, and 30+ products on its open platform. | Keep registration distinct from activity and represent product depth. |
| HDFC Bank | The FY2025 integrated report reports 3.7 crore+ monthly HDFC Bank One engagements, 97% digital financial transactions, and 19.3 lakh SmartHub Vyapar merchants. | Use heterogeneous customer types and over-dispersed activity, not one average transaction rate. |
| ICICI Bank | Its February 2024 release reports more than one crore customers of other banks on iMobile and describes repeat use across several transaction types. | Include non-primary or occasional users and product-specific repeat behaviour. |
| Kotak Mahindra Bank | Its FY2025 integrated report describes a pause in digital onboarding and credit-card issuance until February 2025, alongside deeper engagement with existing 811 customers and a persona-based app strategy. | Allow acquisition, onboarding, and product-mix shocks to change cohort shape. |

## What the public evidence does not support

The reviewed disclosures do not publish a signup-cohort matrix using Pulse's
exact day-window definitions. Registered users, monthly active users,
engagements, transaction share, and product adoption have different units and
denominators. Pulse therefore does not set its retention levels equal to any
reported bank metric and does not label its synthetic rates as peer benchmarks.

The simulator uses the disclosures to justify lifecycle heterogeneity: latent
customer segments, changing acquisition and product mix, delayed activation,
reactivation, and cohort-level operational shocks. Segment weights and shock
sizes remain fictional assumptions that require replacement with internal
event-level data before a real bank decision.

## Sources

- [SBI FY25 Analyst Presentation, digital-presence slide 46](https://sbi.bank.in/documents/17836/0/SBI%2BAnalyst%2BPresentation%2BQ4FY25.pdf/d496fee6-a237-4328-a5ff-7246e4b736b4?t=1746263845521)
- [Axis Bank Integrated Annual Report 2024-25, page 127](https://www.axisbank.com/docs/default-source/annual-reports/for-axis-bank/annual-report-for-the-year-2024-2025.pdf)
- [HDFC Bank Integrated Annual Report 2024-25, pages 7 and 140-141](https://www.hdfc.bank.in/content/dam/hdfcbankpws/in/en/pdf/annual-reports/2024-25/HDFC_Bank_Annual_Report_2024_25-310202.pdf)
- [ICICI Bank iMobile press release, February 2024](https://www.icici.bank.in/about-us/news-room/2024/press-release-icici-banks-imobile-is-used-by-one-crore-customers-from-other-banks)
- [Kotak Mahindra Bank Integrated Annual Report 2024-25, pages 9 and 24-25](https://www.kotak.com/bank/mailers/annualreport/documents/Kotak%20Integrated%20Annual%20Report%202024-25.pdf)
