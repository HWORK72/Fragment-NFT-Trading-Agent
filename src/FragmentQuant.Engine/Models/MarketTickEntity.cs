using System;

namespace FragmentQuant.Engine.Models
{
    public sealed class MarketTickEntity
    {
        public int Id { get; set; }
        public string Collection { get; set; }
        public int GiftNumber { get; set; }
        public decimal PriceTon { get; set; }
        public bool IsBlackBackdrop { get; set; }
        public DateTime CreatedAtUtc { get; set; }

        public MarketTickEntity(
            int id,
            string collection,
            int giftNumber,
            decimal priceTon,
            bool isBlackBackdrop,
            DateTime createdAtUtc)
        {
            Id = id;
            Collection = collection;
            GiftNumber = giftNumber;
            PriceTon = priceTon;
            IsBlackBackdrop = isBlackBackdrop;
            CreatedAtUtc = createdAtUtc;
        }
    }
}
