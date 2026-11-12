using System;
using System.Collections.Generic;
using System.Linq;
using FragmentQuant.Engine.Models;

namespace FragmentQuant.Engine.Analytics
{
    public sealed class OrderbookQuantCalculator
    {
        private readonly ArbitrageAlphaScorer _alphaScorer;
        private readonly decimal _targetDiscountPct;

        public OrderbookQuantCalculator(ArbitrageAlphaScorer alphaScorer, decimal targetDiscountPct)
        {
            _alphaScorer = alphaScorer;
            _targetDiscountPct = targetDiscountPct;
        }

        public List<QuantReport> ComputeSegmentReports(List<MarketTickEntity> ticks)
        {
            List<QuantReport> reports = new List<QuantReport>();
            if (ticks.Count == 0)
            {
                return reports;
            }

            IEnumerable<IGrouping<string, MarketTickEntity>> collectionGroups = ticks
                .GroupBy((MarketTickEntity t) => $"{t.Collection.ToLowerInvariant()}|{t.IsBlackBackdrop}");

            foreach (IGrouping<string, MarketTickEntity> group in collectionGroups)
            {
                List<decimal> sortedPrices = group
                    .Select((MarketTickEntity t) => t.PriceTon)
                    .Where((decimal p) => p > 0.0m)
                    .OrderBy((decimal p) => p)
                    .ToList();

                if (sortedPrices.Count == 0)
                {
                    continue;
                }

                MarketTickEntity firstItem = group.First();
                string collectionName = firstItem.Collection.ToLowerInvariant();
                bool isBlackSegment = firstItem.IsBlackBackdrop;
                int count = sortedPrices.Count;

                decimal floorPrice = sortedPrices[0];
                decimal ceilingPrice = sortedPrices[count - 1];
                decimal medianPrice = CalculateMedian(sortedPrices);
                decimal trimmedMean = CalculateTrimmedMean(sortedPrices, 0.10m);
                decimal stdDev = CalculateStandardDeviation(sortedPrices, trimmedMean);

                decimal spreadPct = floorPrice > 0.0m
                    ? Math.Round(((trimmedMean - floorPrice) / floorPrice) * 100.0m, 2)
                    : 0.0m;

                decimal discountFactor = 1.0m - (_targetDiscountPct / 100.0m);
                decimal recommendedMaxBid = Math.Round(Math.Min(floorPrice, medianPrice) * discountFactor, 2);

                decimal alphaScore = _alphaScorer.ComputeAlphaScore(
                    floorPrice,
                    trimmedMean,
                    medianPrice,
                    stdDev,
                    isBlackSegment,
                    count
                );

                QuantReport report = new QuantReport(
                    collectionName,
                    isBlackSegment,
                    count,
                    Math.Round(floorPrice, 2),
                    Math.Round(ceilingPrice, 2),
                    Math.Round(medianPrice, 2),
                    Math.Round(trimmedMean, 2),
                    Math.Round(stdDev, 2),
                    spreadPct,
                    alphaScore,
                    recommendedMaxBid,
                    DateTime.UtcNow
                );

                reports.Add(report);
            }

            return reports
                .OrderByDescending((QuantReport r) => r.AlphaOpportunityScore)
                .ToList();
        }

        private static decimal CalculateMedian(List<decimal> sortedValues)
        {
            int count = sortedValues.Count;
            int middleIndex = count / 2;
            if (count % 2 == 0)
            {
                return (sortedValues[middleIndex - 1] + sortedValues[middleIndex]) / 2.0m;
            }
            return sortedValues[middleIndex];
        }

        private static decimal CalculateTrimmedMean(List<decimal> sortedValues, decimal trimFraction)
        {
            int count = sortedValues.Count;
            if (count < 10)
            {
                return sortedValues.Average();
            }

            int trimCount = (int)(count * trimFraction);
            List<decimal> trimmedSlice = sortedValues
                .Skip(trimCount)
                .Take(count - (trimCount * 2))
                .ToList();

            return trimmedSlice.Count > 0 ? trimmedSlice.Average() : sortedValues.Average();
        }

        private static decimal CalculateStandardDeviation(List<decimal> values, decimal mean)
        {
            if (values.Count <= 1)
            {
                return 0.0m;
            }

            double varianceSum = 0.0;
            foreach (decimal val in values)
            {
                double diff = (double)(val - mean);
                varianceSum += diff * diff;
            }

            double variance = varianceSum / (values.Count - 1);
            return (decimal)Math.Sqrt(variance);
        }
    }
}
