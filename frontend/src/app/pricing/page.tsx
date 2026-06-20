import { Check } from "lucide-react"
import PricingCard from "./components/pricing-card"

export default function PricingPage() {
    const plans = [
        {
            name: "Free / Enthusiast",
            price: "$0/year",
            description: "Perfect for getting started with AI automation",
            features: ["20,000 Tokens per day", "1 Free AI Agent Deployment", "Community support", "Basic analytics"],
            excludedFeatures: ["Advanced features"],
            callToAction: "Start Free Trial",
            popular: false,
        },
        {
            name: "Pro",
            price: "$99.99/year",
            description: "Advanced features for growing businesses",
            features: [
                "5 Million Tokens per month",
                "Unlimited AI Agents Deployment",
                "Unlimited fine-tuning",
                "Advanced analytics & reporting",
                "Priority support",
            ],
            excludedFeatures: [],
            callToAction: "Get Started",
            popular: true,
        },
        {
            name: "Enterprise",
            price: "Custom",
            description: "Tailored solutions for large organizations",
            features: [
                "Custom token allocation",
                "Dedicated AI engineering team",
                "Custom API integration",
                "SLA guarantees",
                "Advanced security features",
            ],
            excludedFeatures: [],
            callToAction: "Contact Sales",
            popular: false,
        },
    ]

    return (
        <div className="min-h-screen ">
            {/* TODO: ya eauta monthly ra yearly ko toggle hal */}
            <div className="container mx-auto px-4 py-16">
                <div className="text-center mb-16">
                    <h1 className="text-4xl md:text-5xl font-bold mb-4 text-foreground">Simple, Transparent Pricing</h1>
                    <p className="text-xl text-muted-foreground max-w-2xl mx-auto">
                        Choose the perfect plan for your AI automation needs. Scale as you grow.
                    </p>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-3 gap-8 max-w-6xl mx-auto">
                    {plans.map((plan) => (
                        <PricingCard key={plan.name} plan={plan} />
                    ))}
                </div>

                <div className="mt-16 text-center">
                    <h2 className="text-2xl font-semibold mb-4 text-foreground">All Plans Include</h2>
                    <div className="flex flex-wrap justify-center gap-4 max-w-3xl mx-auto">
                        {["24/7 System Monitoring", "99.9% Uptime", "Secure Data Storage", "Regular Updates"].map((feature) => (
                            <div key={feature} className="bg-card rounded-lg px-6 py-3 shadow-sm border">
                                <div className="flex items-center gap-2">
                                    <Check className="h-5 w-5 text-emerald-500" />
                                    <span className="text-card-foreground">{feature}</span>
                                </div>
                            </div>
                        ))}
                    </div>
                </div>

                <div className="mt-16 text-center bg-card rounded-xl p-8 shadow-sm max-w-3xl mx-auto border">
                    <h2 className="text-2xl font-semibold mb-2 text-card-foreground">Need a Custom Solution?</h2>
                    <p className="text-muted-foreground mb-6">
                        Contact our sales team to discuss your specific requirements and get a tailored quote.
                    </p>
                    <button className="bg-primary hover:bg-primary/90 text-primary-foreground font-medium py-3 px-6 rounded-lg transition-colors">
                        Contact Sales
                    </button>
                </div>
            </div>
        </div>
    )
}
