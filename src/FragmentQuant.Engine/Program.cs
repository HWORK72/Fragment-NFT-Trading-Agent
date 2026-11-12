using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Linq;
using DotNetEnv;
using FragmentQuant.Engine.Analytics;
using FragmentQuant.Engine.Data;
using FragmentQuant.Engine.Logging;
using FragmentQuant.Engine.Models;
using FragmentQuant.Engine.Risk;

namespace FragmentQuant.Engine
{
    public static class Program
    {
        public static int Main(string[] args)
        {
            bool isSubordinate = args.Any((string a) => a == "--subordinate");
            string rootDirectory = ResolveProjectRootDirectory();
            using InstantFileLogger logger = new InstantFileLogger("FragmentQuantCSharp", rootDirectory, isSubordinate);

            try
            {
                logger.LogInfo("Initializing C# (.NET) High-Frequency Quantitative & Risk Engine...");
                string envFilePath = Path.Combine(rootDirectory, ".env");
                if (File.Exists(envFilePath))
                {
                    Env.Load(envFilePath);
                    logger.LogInfo("Loaded environment configuration from root .env");
                }

                decimal walletBalance = ParseEnvDecimal("TON_WALLET_BALANCE", 2.0m);
                decimal gasReserve = ParseEnvDecimal("MIN_BALANCE_RESERVE_TON", 0.2m);
                decimal maxSingleBid = ParseEnvDecimal("MAX_BID_PER_ITEM_TON", 10.0m);
                decimal dailyBudget = ParseEnvDecimal("DAILY_BUDGET_TON", 10.0m);
                decimal targetDiscountPct = ParseEnvDecimal("TARGET_DISCOUNT_PCT", 15.0m);

                SqliteMarketRepository repository = new SqliteMarketRepository(rootDirectory, logger);
                repository.EnsureSchemaExists();

                List<MarketTickEntity> ticks = repository.LoadRecentMarketTicks(1000);
                List<TradeDecisionEntity> decisions = repository.LoadTradeDecisions(500);

                logger.LogInfo($"Loaded {ticks.Count} market ticks and {decisions.Count} trade decisions from SQLite.");

                ArbitrageAlphaScorer alphaScorer = new ArbitrageAlphaScorer();
                OrderbookQuantCalculator calculator = new OrderbookQuantCalculator(alphaScorer, targetDiscountPct);

                List<QuantReport> reports = calculator.ComputeSegmentReports(ticks);

                PortfolioRiskAuditor riskAuditor = new PortfolioRiskAuditor(
                    logger,
                    walletBalance,
                    gasReserve,
                    maxSingleBid,
                    dailyBudget
                );

                riskAuditor.ExecutePortfolioAudit(reports, decisions);
                logger.LogInfo("C# Quantitative Risk & Orderbook Engine cycle completed successfully.");
                return 0;
            }
            catch (Exception ex)
            {
                logger.LogError("Fatal unhandled error in C# Quantitative Engine", ex);
                return 1;
            }
        }

        private static string ResolveProjectRootDirectory()
        {
            DirectoryInfo? current = new DirectoryInfo(AppContext.BaseDirectory);
            while (current != null)
            {
                string envCandidate = Path.Combine(current.FullName, ".env");
                string mainPyCandidate = Path.Combine(current.FullName, "main.py");
                if (File.Exists(envCandidate) || File.Exists(mainPyCandidate))
                {
                    return current.FullName;
                }
                current = current.Parent;
            }
            return Directory.GetCurrentDirectory();
        }

        private static decimal ParseEnvDecimal(string key, decimal fallbackValue)
        {
            string? rawValue = Environment.GetEnvironmentVariable(key);
            if (string.IsNullOrWhiteSpace(rawValue))
            {
                return fallbackValue;
            }

            if (decimal.TryParse(rawValue.Trim(), NumberStyles.Any, CultureInfo.InvariantCulture, out decimal parsed))
            {
                return parsed;
            }

            return fallbackValue;
        }
    }
}