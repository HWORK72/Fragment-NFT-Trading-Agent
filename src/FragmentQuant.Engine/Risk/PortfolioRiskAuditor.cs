using System;
using System.Collections.Generic;
using System.Linq;
using FragmentQuant.Engine.Logging;
using FragmentQuant.Engine.Models;

namespace FragmentQuant.Engine.Risk
{
    public sealed class PortfolioRiskAuditor
    {
        private readonly InstantFileLogger _logger;
        private readonly decimal _walletBalanceTon;
        private readonly decimal _gasReserveTon;
        private readonly decimal _maxSingleBidTon;
        private readonly decimal _dailyBudgetTon;

        public PortfolioRiskAuditor(
            InstantFileLogger logger,
            decimal walletBalanceTon,
            decimal gasReserveTon,
            decimal maxSingleBidTon,
            decimal dailyBudgetTon)
        {
            _logger = logger;
            _walletBalanceTon = walletBalanceTon;
            _gasReserveTon = gasReserveTon;
            _maxSingleBidTon = maxSingleBidTon;
            _dailyBudgetTon = dailyBudgetTon;
        }

        public void ExecutePortfolioAudit(
            List<QuantReport> reports,
            List<TradeDecisionEntity> recentDecisions)
        {
            decimal spendableCapital = Math.Max(0.0m, _walletBalanceTon - _gasReserveTon);
            int totalEvaluated = recentDecisions.Count;
            int totalApproved = recentDecisions.Count((TradeDecisionEntity d) => d.Verdict == "ENTER");
            int totalRejected = recentDecisions.Count((TradeDecisionEntity d) => d.Verdict == "REJECT");

            decimal approvalRatePct = totalEvaluated > 0
                ? Math.Round(((decimal)totalApproved / totalEvaluated) * 100.0m, 2)
                : 0.0m;

            _logger.LogInfo("=== C# QUANTITATIVE RISK & PORTFOLIO AUDIT ===");
            _logger.LogInfo(
                $"Capital Allocation: Total={_walletBalanceTon:F3} TON | GasReserve={_gasReserveTon:F3} TON | Spendable={spendableCapital:F3} TON"
            );
            _logger.LogInfo(
                $"Risk Limits: MaxSingleBid={_maxSingleBidTon:F2} TON | DailyBudget={_dailyBudgetTon:F2} TON"
            );
            _logger.LogInfo(
                $"Decision History: Total={totalEvaluated} | Approved(ENTER)={totalApproved} | Rejected={totalRejected} | ApprovalRate={approvalRatePct}%"
            );

            foreach (QuantReport report in reports)
            {
                string backdropTag = report.IsBlackBackdropSegment ? "BLACK-RARE" : "STANDARD";
                decimal kellyFraction = ComputeKellyAllocationPct(report.AlphaOpportunityScore, report.SpreadPercentage);
                decimal optimalPositionTon = Math.Round(Math.Min(_maxSingleBidTon, spendableCapital * (kellyFraction / 100.0m)), 2);

                _logger.LogInfo(
                    $"Segment [{report.CollectionSlug} | {backdropTag}] -> Samples={report.SampleCount} | Floor={report.FloorPriceTon} TON | TrimmedAvg={report.TrimmedMeanPriceTon} TON | Median={report.MedianPriceTon} TON | Spread={report.SpreadPercentage}% | AlphaScore={report.AlphaOpportunityScore}/100 | TargetEntryCap={report.RecommendedMaxBidTon} TON | KellyAllocation={optimalPositionTon} TON"
                );
            }

            _logger.LogInfo("==============================================");
        }

        private static decimal ComputeKellyAllocationPct(decimal alphaScore, decimal spreadPct)
        {
            if (alphaScore < 25.0m || spreadPct <= 0.0m)
            {
                return 0.0m;
            }

            decimal winProbability = Math.Clamp(alphaScore / 100.0m, 0.10m, 0.85m);
            decimal lossProbability = 1.0m - winProbability;
            decimal payoffOdds = Math.Clamp(spreadPct / 20.0m, 0.50m, 5.0m);

            decimal rawKelly = winProbability - (lossProbability / payoffOdds);
            decimal halfKellyPct = Math.Max(0.0m, (rawKelly * 0.5m) * 100.0m);

            return Math.Round(Math.Clamp(halfKellyPct, 0.0m, 50.0m), 2);
        }
    }
}
