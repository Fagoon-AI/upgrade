"use client";

import React, { useState } from "react";
import {
  Search,
  Star,
  DollarSign,
  Clock,
  Tag,
  Sparkles,
  ChevronRight,
  ArrowRight,
  Zap,
  Globe,
  Shield,
} from "lucide-react";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
interface AIAgent {
  id: number;
  name: string;
  description: string;
  price: number;
  rentPrice: number;
  category: string;
  rating: number;
  reviews: number;
  creator: string;
  image: string;
  features: string[];
  stats: {
    accuracy: number;
    speed: number;
    reliability: number;
  };
}

const AIMarketplace: React.FC = () => {
  // State Management
  const [searchQuery, setSearchQuery] = useState<string>("");
  const [category, setCategory] = useState<string>("all");
  const [hoveredCard, setHoveredCard] = useState<number | null>(null);

  // AI Agents Dataset
  const aiAgents: AIAgent[] = [
    {
      id: 1,
      name: "Enterprise Content Intelligence",
      description:
        "Advanced AI-driven content optimization engine with enterprise-grade NLP capabilities",
      price: 299,
      rentPrice: 29,
      category: "Enterprise",
      rating: 4.8,
      reviews: 156,
      creator: "DataMind Labs",
      image: "/enterprise-content-intelligence.webp",
      features: [
        "Enterprise-grade NLP",
        "Multi-language Support",
        "Advanced Analytics",
      ],
      stats: {
        accuracy: 98,
        speed: 95,
        reliability: 99,
      },
    },
    {
      id: 2,
      name: "Neural Analytics Suite",
      description:
        "Enterprise business intelligence powered by deep learning neural networks",
      price: 499,
      rentPrice: 49,
      category: "Analytics",
      rating: 4.6,
      reviews: 89,
      creator: "AI Solutions Inc",
      image: "/neural-analytics-suite.webp",
      features: [
        "Predictive Modeling",
        "Real-time Analysis",
        "Custom Dashboards",
      ],
      stats: {
        accuracy: 96,
        speed: 98,
        reliability: 97,
      },
    },
    {
      id: 3,
      name: "Quantum Support Intelligence",
      description:
        "Next-generation customer experience automation with quantum-inspired algorithms",
      price: 399,
      rentPrice: 39,
      category: "Enterprise",
      rating: 4.7,
      reviews: 234,
      creator: "ServiceTech AI",
      image: "/quantum-support-intelligence.webp",
      features: [
        "24/7 Automation",
        "Sentiment Analysis",
        "Multi-channel Support",
      ],
      stats: {
        accuracy: 97,
        speed: 99,
        reliability: 98,
      },
    },
  ];

  // Filtering Logic
  const filteredAgents = aiAgents.filter(
    (agent) =>
      (category === "all" || agent.category === category) &&
      agent.name.toLowerCase().includes(searchQuery.toLowerCase())
  );

  return (
    <div className="min-h-screen">
      <div className="max-w-7xl mx-auto px-8 py-20">
        {/* Hero Section */}
        <section className="text-center mb-20 relative">
          <div className="absolute inset-0 -z-10">
            <div className="absolute inset-0 bg-grid-slate-200/50 dark:bg-grid-slate-800/50 bg-[size:40px_40px] [mask-image:radial-gradient(ellipse_80%_80%_at_50%_50%,black,transparent)]" />
          </div>

          <div className="inline-flex items-center justify-center gap-2 mb-6 px-4 py-2 rounded-full bg-blue-500/10 dark:bg-blue-400/10">
            <Sparkles className="h-5 w-5 text-blue-500 dark:text-blue-400" />
            <span className="text-sm font-medium text-blue-600 dark:text-blue-400">
              Enterprise AI Solutions
            </span>
          </div>

          <h1 className="text-6xl font-bold mb-6 bg-clip-text text-transparent bg-gradient-to-r from-slate-900 to-slate-700 dark:from-slate-200 dark:to-slate-400">
            Intelligence Marketplace
          </h1>

          <p className="text-lg text-slate-600 dark:text-slate-400 max-w-2xl mx-auto">
            Discover enterprise-grade artificial intelligence solutions
            engineered for exceptional performance.
          </p>
        </section>

        {/* Performance Statistics */}
        <section className="grid grid-cols-1 md:grid-cols-3 gap-8 mb-16">
          {[
            { icon: Zap, label: "Processing Speed", value: "10ms" },
            { icon: Globe, label: "Global Deployment", value: "99.9%" },
            {
              icon: Shield,
              label: "Enterprise Security",
              value: "Military-grade",
            },
          ].map(({ icon: Icon, label, value }) => (
            <div
              key={label}
              className="p-6 rounded-2xl bg-white/50 dark:bg-slate-800/50 backdrop-blur-sm border border-slate-200 dark:border-slate-700"
            >
              <Icon className="h-6 w-6 text-blue-500 dark:text-blue-400 mb-4" />
              <div className="text-2xl font-semibold text-slate-900 dark:text-slate-200 mb-1">
                {value}
              </div>
              <div className="text-sm text-slate-600 dark:text-slate-400">
                {label}
              </div>
            </div>
          ))}
        </section>

        {/* Search and Filtering Section */}
        <section className="flex flex-col md:flex-row gap-4 mb-16">
          <div className="flex-1 relative group">
            <Input
              type="text"
              placeholder="Search enterprise solutions"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="h-14 pl-12 pr-4 rounded-2xl bg-white/50 dark:bg-slate-800/50 backdrop-blur-sm border-slate-200 dark:border-slate-700 focus:ring-2 focus:ring-blue-500 dark:focus:ring-blue-400 transition-all"
            />
            <Search className="absolute left-4 top-4 h-5 w-5 text-slate-400 dark:text-slate-500 group-hover:text-blue-500 dark:group-hover:text-blue-400 transition-colors" />
          </div>

          <Select value={category} onValueChange={setCategory}>
            <SelectTrigger className="w-full md:w-64 h-14 rounded-2xl bg-white/50 dark:bg-slate-800/50 backdrop-blur-sm border-slate-200 dark:border-slate-700">
              <SelectValue placeholder="Solution Category" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All Categories</SelectItem>
              <SelectItem value="Enterprise">Enterprise Solutions</SelectItem>
              <SelectItem value="Analytics">Advanced Analytics</SelectItem>
            </SelectContent>
          </Select>
        </section>

        {/* AI Solutions Grid */}
        <section className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-8">
          {filteredAgents.map((agent) => (
            <Card
              key={agent.id}
              onMouseEnter={() => setHoveredCard(agent.id)}
              onMouseLeave={() => setHoveredCard(null)}
              className="group relative overflow-hidden rounded-2xl border-0 bg-white/50 dark:bg-slate-800/50 backdrop-blur-sm hover:shadow-2xl hover:-translate-y-1 transition-all duration-300"
            >
              {/* <div className="absolute inset-0 bg-gradient-to-br from-blue-500/0 via-blue-500/0 to-blue-500/0 group-hover:from-blue-500/5 group-hover:via-blue-500/5 group-hover:to-blue-500/10 dark:group-hover:from-blue-400/5 dark:group-hover:via-blue-400/5 dark:group-hover:to-blue-400/10 transition-all duration-300" /> */}

              <CardHeader className="p-0">
                <div className="relative">
                  <img
                    src={agent.image}
                    alt={agent.name}
                    className="w-full h-48 object-cover"
                  />
                  <div className="absolute inset-0 bg-gradient-to-t from-slate-900/60 to-transparent" />
                  <Badge className="absolute top-4 right-4 bg-white/90 dark:bg-slate-800/90 text-slate-900 dark:text-slate-200 backdrop-blur-sm">
                    {agent.category}
                  </Badge>
                </div>
              </CardHeader>

              <CardContent className="p-8">
                <div className="mb-8">
                  <div className="flex items-center gap-2 mb-2">
                    <Badge
                      variant="secondary"
                      className="bg-blue-500/10 text-blue-600 dark:text-blue-400"
                    >
                      <Star className="h-3 w-3 mr-1 fill-current" />
                      {agent.rating}
                    </Badge>
                    <span className="text-sm text-slate-600 dark:text-slate-400">
                      {agent.reviews} enterprise reviews
                    </span>
                  </div>

                  <CardTitle
                  className="text-xl font-semibold mb-3 text-slate-900 dark:text-slate-200">
                    {agent.name}
                  </CardTitle>

                  <p className="text-sm leading-relaxed text-slate-600 dark:text-slate-400">
                    {agent.description}
                  </p>
                </div>

                {/* Performance Metrics */}
                <div className="space-y-2 mb-6">
                  {Object.entries(agent.stats).map(([key, value]) => (
                    <div
                      key={key}
                      className="relative h-2 rounded-full bg-slate-200 dark:bg-slate-700 overflow-hidden"
                    >
                      <div
                        className="absolute inset-y-0 left-0 bg-blue-500 dark:bg-blue-400 transition-all duration-1000 ease-out rounded-full"
                        style={{
                          width: hoveredCard === agent.id ? `${value}%` : "0%",
                        }}
                      />
                      <div className="absolute -top-6 left-0 text-xs text-slate-600 dark:text-slate-400 capitalize">
                        {key}
                      </div>
                      <div className="absolute -top-6 right-0 text-xs text-slate-600 dark:text-slate-400">
                        {value}%
                      </div>
                    </div>
                  ))}
                </div>

                <div className="space-y-6">
                  <div className="grid grid-cols-1 gap-2">
                    {agent.features.map((feature, index) => (
                      <div
                        key={index}
                        className="flex items-center gap-2 text-sm text-slate-600 dark:text-slate-400"
                      >
                        <div className="h-1.5 w-1.5 rounded-full bg-blue-500 dark:bg-blue-400" />
                        {feature}
                      </div>
                    ))}
                  </div>

                  <div className="flex items-center justify-between text-sm pt-4 border-t border-slate-200 dark:border-slate-700">
                    <div>
                      <div className="flex items-center gap-1 mb-1">
                        <DollarSign className="h-4 w-4 text-slate-400 dark:text-slate-500" />
                        <span className="font-semibold text-lg text-slate-900 dark:text-slate-200">
                          ${agent.price}
                        </span>
                      </div>
                      <span className="text-slate-600 dark:text-slate-400">
                        Enterprise license
                      </span>
                    </div>
                    <div>
                      <div className="flex items-center gap-1 mb-1">
                        <Clock className="h-4 w-4 text-slate-400 dark:text-slate-500" />
                        <span className="font-semibold text-lg text-slate-900 dark:text-slate-200">
                          ${agent.rentPrice}
                        </span>
                      </div>
                      <span className="text-slate-600 dark:text-slate-400">
                        Monthly subscription
                      </span>
                    </div>
                  </div>

                  <div className="space-y-3">
                    <Button
                  onClick={() => window.open(`/checkout?product=${agent.name.toLowerCase().split(' ')[0]}`, '_blank')}
                    className="w-full h-12 bg-slate-900 dark:bg-blue-500 hover:bg-slate-800 dark:hover:bg-blue-600 text-white rounded-xl group z-[100]">
                      <span className="text-xs">
                        Deploy Enterprise Solution
                      </span>
                      <ArrowRight className="h-4 w-4 ml-2 group-hover:translate-x-1 transition-transform" />
                    </Button>
                    <Button
                      variant="ghost"
                      className="w-full h-12 text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-700 rounded-xl group"
                    >
                      <span>Request Demo</span>
                      <ChevronRight className="h-4 w-4 ml-2 group-hover:translate-x-1 transition-transform" />
                    </Button>
                  </div>
                </div>
              </CardContent>
            </Card>
          ))}
        </section>

        {/* Call to Action */}
        <section className="mt-20 text-center">
          <Button
            size="lg"
            className="h-14 px-8 bg-gradient-to-r from-blue-500 to-blue-600 dark:from-blue-600 dark:to-blue-700 hover:from-blue-600 hover:to-blue-700 dark:hover:from-blue-700 dark:hover:to-blue-800 text-white rounded-xl shadow-lg shadow-blue-500/20 dark:shadow-blue-500/10 group"
          >
            <Tag className="h-5 w-5 mr-2 group-hover:rotate-12 transition-transform" />
            <span>List Enterprise Solution</span>
          </Button>
        </section>
      </div>
    </div>
  );
};

export default AIMarketplace;
