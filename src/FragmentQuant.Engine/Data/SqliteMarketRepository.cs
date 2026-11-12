using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using FragmentQuant.Engine.Logging;
using FragmentQuant.Engine.Models;
using Microsoft.Data.Sqlite;

namespace FragmentQuant.Engine.Data
{
    public sealed class SqliteMarketRepository
    {
        private readonly string _connectionString;
        private readonly string _dbFilePath;
        private readonly InstantFileLogger _logger;

        public SqliteMarketRepository(string rootDirectoryPath, InstantFileLogger logger)
        {
            _logger = logger;
            _dbFilePath = Path.Combine(rootDirectoryPath, "fragment_market.db");
            _connectionString = $"Data Source={_dbFilePath};Mode=ReadWriteCreate;";
        }

        public void EnsureSchemaExists()
        {
            try
            {
                using SqliteConnection connection = new SqliteConnection(_connectionString);
                connection.Open();

                using SqliteCommand command = connection.CreateCommand();
                command.CommandText = @"
                    CREATE TABLE IF NOT EXISTS market_ticks (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        collection VARCHAR(64),
                        gift_num INTEGER,
                        price_ton NUMERIC(12, 2),
                        is_black_backdrop BOOLEAN,
                        created_at DATETIME
                    );
                    CREATE TABLE IF NOT EXISTS trade_decisions (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        auction_id VARCHAR(64),
                        collection VARCHAR(64),
                        price_ton NUMERIC(12, 2),
                        floor_at_execution NUMERIC(12, 2),
                        verdict VARCHAR(16),
                        reason VARCHAR(255),
                        created_at DATETIME
                    );";
                command.ExecuteNonQuery();
                _logger.LogInfo($"SQLite database schema verified at: {_dbFilePath}");
            }
            catch (Exception ex)
            {
                _logger.LogError("Failed initializing SQLite schema in C# repository", ex);
                throw;
            }
        }

        public List<MarketTickEntity> LoadRecentMarketTicks(int limitCount)
        {
            List<MarketTickEntity> ticks = new List<MarketTickEntity>();
            try
            {
                using SqliteConnection connection = new SqliteConnection(_connectionString);
                connection.Open();

                using SqliteCommand command = connection.CreateCommand();
                command.CommandText = @"
                    SELECT id, collection, gift_num, price_ton, is_black_backdrop, created_at
                    FROM market_ticks
                    ORDER BY id DESC
                    LIMIT $limit;";
                command.Parameters.AddWithValue("$limit", limitCount);

                using SqliteDataReader reader = command.ExecuteReader();
                while (reader.Read())
                {
                    int id = reader.GetInt32(0);
                    string collection = reader.IsDBNull(1) ? "unknown" : reader.GetString(1);
                    int giftNum = reader.IsDBNull(2) ? 0 : reader.GetInt32(2);

                    decimal priceTon = 0.0m;
                    if (!reader.IsDBNull(3))
                    {
                        string rawPrice = Convert.ToString(reader.GetValue(3), CultureInfo.InvariantCulture) ?? "0";
                        decimal.TryParse(rawPrice, NumberStyles.Any, CultureInfo.InvariantCulture, out priceTon);
                    }

                    bool isBlack = !reader.IsDBNull(4) && reader.GetBoolean(4);
                    DateTime createdAt = DateTime.UtcNow;
                    if (!reader.IsDBNull(5))
                    {
                        string rawDate = reader.GetString(5);
                        DateTime.TryParse(rawDate, CultureInfo.InvariantCulture, DateTimeStyles.AdjustToUniversal, out createdAt);
                    }

                    MarketTickEntity entity = new MarketTickEntity(
                        id,
                        collection,
                        giftNum,
                        priceTon,
                        isBlack,
                        createdAt
                    );
                    ticks.Add(entity);
                }
            }
            catch (Exception ex)
            {
                _logger.LogError("Error loading market ticks from SQLite", ex);
            }

            return ticks;
        }

        public List<TradeDecisionEntity> LoadTradeDecisions(int limitCount)
        {
            List<TradeDecisionEntity> decisions = new List<TradeDecisionEntity>();
            try
            {
                using SqliteConnection connection = new SqliteConnection(_connectionString);
                connection.Open();

                using SqliteCommand command = connection.CreateCommand();
                command.CommandText = @"
                    SELECT id, auction_id, collection, price_ton, floor_at_execution, verdict, reason, created_at
                    FROM trade_decisions
                    ORDER BY id DESC
                    LIMIT $limit;";
                command.Parameters.AddWithValue("$limit", limitCount);

                using SqliteDataReader reader = command.ExecuteReader();
                while (reader.Read())
                {
                    int id = reader.GetInt32(0);
                    string auctionId = reader.IsDBNull(1) ? "unknown" : reader.GetString(1);
                    string collection = reader.IsDBNull(2) ? "unknown" : reader.GetString(2);

                    decimal priceTon = 0.0m;
                    if (!reader.IsDBNull(3))
                    {
                        string rawPrice = Convert.ToString(reader.GetValue(3), CultureInfo.InvariantCulture) ?? "0";
                        decimal.TryParse(rawPrice, NumberStyles.Any, CultureInfo.InvariantCulture, out priceTon);
                    }

                    decimal floorTon = 0.0m;
                    if (!reader.IsDBNull(4))
                    {
                        string rawFloor = Convert.ToString(reader.GetValue(4), CultureInfo.InvariantCulture) ?? "0";
                        decimal.TryParse(rawFloor, NumberStyles.Any, CultureInfo.InvariantCulture, out floorTon);
                    }

                    string verdict = reader.IsDBNull(5) ? "REJECT" : reader.GetString(5);
                    string reason = reader.IsDBNull(6) ? "" : reader.GetString(6);

                    DateTime createdAt = DateTime.UtcNow;
                    if (!reader.IsDBNull(7))
                    {
                        string rawDate = reader.GetString(7);
                        DateTime.TryParse(rawDate, CultureInfo.InvariantCulture, DateTimeStyles.AdjustToUniversal, out createdAt);
                    }

                    TradeDecisionEntity entity = new TradeDecisionEntity(
                        id,
                        auctionId,
                        collection,
                        priceTon,
                        floorTon,
                        verdict,
                        reason,
                        createdAt
                    );
                    decisions.Add(entity);
                }
            }
            catch (Exception ex)
            {
                _logger.LogError("Error loading trade decisions from SQLite", ex);
            }

            return decisions;
        }
    }
}
