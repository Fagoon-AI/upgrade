import { Check, X } from "lucide-react"
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"

interface PlanFeature {
    name: string
    included: boolean
}

interface PricingCardProps {
    plan: {
        name: string
        price: string
        description: string
        features: string[]
        excludedFeatures?: string[]
        callToAction: string
        popular: boolean
    }
}

export default function PricingCard({ plan }: PricingCardProps) {
    // Combine included and excluded features
    const allFeatures = [
        ...plan.features.map((feature) => ({ name: feature, included: true })),
        ...(plan.excludedFeatures || []).map((feature) => ({ name: feature, included: false })),
    ]

    return (
        <Card className={`relative flex flex-col h-full ${plan.popular ? "border-primary shadow-lg" : ""}`}>
            {plan.popular && <Badge className="absolute -top-3 right-4 bg-primary hover:bg-primary">Most Popular</Badge>}

            <CardHeader>
                <CardTitle className="text-2xl font-bold">{plan.name}</CardTitle>
                <CardDescription className="mt-2">{plan.description}</CardDescription>
            </CardHeader>

            <CardContent className="flex-grow">
                <div className="mb-6">
                    <span className="text-3xl font-bold">{plan.price}</span>
                    {plan.price !== "Custom" && <span className="text-muted-foreground ml-1">/year</span>}
                </div>

                <div className="space-y-3">
                    {allFeatures.map((feature, index) => (
                        <div key={index} className="flex items-start gap-2">
                            {feature.included ? (
                                <Check className="h-5 w-5 text-emerald-500 shrink-0 mt-0.5" />
                            ) : (
                                <X className="h-5 w-5 text-muted-foreground/40 shrink-0 mt-0.5" />
                            )}
                            <span className={feature.included ? "text-foreground" : "text-muted-foreground/70"}>{feature.name}</span>
                        </div>
                    ))}
                </div>
            </CardContent>

            <CardFooter>
                <Button
                    className={`w-full ${plan.popular
                            ? "bg-primary hover:bg-primary/90 text-primary-foreground"
                            : plan.name === "Enterprise"
                                ? "bg-secondary hover:bg-secondary/90 text-secondary-foreground"
                                : ""
                        }`}
                    variant={plan.popular ? "default" : plan.name === "Enterprise" ? "secondary" : "outline"}
                >
                    {plan.callToAction}
                </Button>
            </CardFooter>
        </Card>
    )
}
