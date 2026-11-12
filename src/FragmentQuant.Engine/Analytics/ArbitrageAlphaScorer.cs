using System;

namespace FragmentQuant.Engine.Analytics
{
    public sealed class ArbitrageAlphaScorer
    {
        public decimal ComputeAlphaScore(
            decimal floorPrice,
            decimal trimmedMean,
            decimal medianPrice,
            decimal standardDeviation,
            bool isBlackBackdrop,
            int sampleSize)
        {
            if (floorPrice <= 0.0m || sampleSize <= 0)
            {
                return 0.0m;
            }

            decimal meanToFloorRatio = trimmedMean / floorPrice;
            decimal spreadComponent = Math.Clamp((meanToFloorRatio - 1.0m) * 40.0m, 0.0m, 50.0m);

            decimal liquidityFactor = Math.Clamp((decimal)sampleSize / 60.0m, 0.1m, 1.5m) * 20.0m;

            decimal rarityBonus = isBlackBackdrop ? 25.0m : 5.0m;

            decimal volatilityRatio = trimmedMean > 0.0m ? standardDeviation / trimmedMean : 0.0m;
            decimal stabilityAdjustment = volatilityRatio > 1.5m ? -10.0m : 5.0m;

            decimal rawScore = spreadComponent + liquidityFactor + rarityBonus + stabilityAdjustment;
            return Math.Round(Math.Clamp(rawScore, 0.0m, 100.0m), 2);
        }
    }
}
