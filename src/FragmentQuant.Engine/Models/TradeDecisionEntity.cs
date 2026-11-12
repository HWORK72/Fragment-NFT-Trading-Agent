using System;

namespace FragmentQuant.Engine.Models
{
    public sealed class TradeDecisionEntity
    {
        public int Id { get; set; }
        public string AuctionId { get; set; }
        public string Collection { get; set; }
        public decimal PriceTon { get; set; }
        public decimal FloorAtExecutionTon { get; set; }
        public string Verdict { get; set; }
        public string Reason { get; set; }
        public DateTime CreatedAtUtc { get; set; }

        public TradeDecisionEntity(
            int id,
            string auctionId,
            string collection,
            decimal priceTon,
            decimal floorAtExecutionTon,
            string verdict,
            string reason,
            DateTime createdAtUtc)
        {
            Id = id;
            AuctionId = auctionId;
            Collection = collection;
            PriceTon = priceTon;
            FloorAtExecutionTon = floorAtExecutionTon;
            Verdict = verdict;
            Reason = reason;
            CreatedAtUtc = createdAtUtc;
        }
    }
}
