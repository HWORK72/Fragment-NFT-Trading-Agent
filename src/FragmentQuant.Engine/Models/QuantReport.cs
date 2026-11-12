using System;

namespace FragmentQuant.Engine.Models
{
    public sealed class QuantReport
    {
        public string CollectionSlug { get; set; }
        public bool IsBlackBackdropSegment { get; set; }
        public int SampleCount { get; set; }
        public decimal FloorPriceTon { get; set; }
        public decimal CeilingPriceTon { get; set; }
        public decimal MedianPriceTon { get; set; }
        public decimal TrimmedMeanPriceTon { get; set; }
        public decimal StandardDeviationTon { get; set; }
        public decimal SpreadPercentage { get; set; }
        public decimal AlphaOpportunityScore { get; set; }
        public decimal RecommendedMaxBidTon { get; set; }
        public DateTime GeneratedAtUtc { get; set; }

        public QuantReport(
            string collectionSlug,
            bool isBlackBackdropSegment,
            int sampleCount,
            decimal floorPriceTon,
            decimal ceilingPriceTon,
            decimal medianPriceTon,
            decimal trimmedMeanPriceTon,
            decimal standardDeviationTon,
            decimal spreadPercentage,
            decimal alphaOpportunityScore,
            decimal recommendedMaxBidTon,
            DateTime generatedAtUtc)
        {
            CollectionSlug = collectionSlug;
            IsBlackBackdropSegment = isBlackBackdropSegment;
            SampleCount = sampleCount;
            FloorPriceTon = floorPriceTon;
            CeilingPriceTon = ceilingPriceTon;
            MedianPriceTon = medianPriceTon;
            TrimmedMeanPriceTon = trimmedMeanPriceTon;
            StandardDeviationTon = standardDeviationTon;
            SpreadPercentage = spreadPercentage;
            AlphaOpportunityScore = alphaOpportunityScore;
            RecommendedMaxBidTon = recommendedMaxBidTon;
            GeneratedAtUtc = generatedAtUtc;
        }
    }
}