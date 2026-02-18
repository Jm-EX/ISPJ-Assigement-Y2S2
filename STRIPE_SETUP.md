# Stripe Setup for Casino Chip Purchases

## Environment Variable Required

Add this to your Render environment variables:

```
STRIPE_SECRET_KEY=sk_test_YOUR_ACTUAL_KEY
```

## Test Mode

The app is configured to use Stripe test mode.

**Test Card Number**: `4242 4242 4242 4242`
- Any future expiration date
- Any 3-digit CVC
- Any billing ZIP code

## Chip Packages

- $100 chips for $5.00
- $500 chips for $20.00
- $1,000 chips for $35.00
- $5,000 chips for $150.00

## How It Works

1. User clicks '+' button next to balance
2. Selects a chip package
3. Redirected to Stripe Checkout
4. Enters test card: 4242 4242 4242 4242
5. On success, chips are automatically added to balance
6. Redirected back to Blackjack game
