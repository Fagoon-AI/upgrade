"use client";

import { useEffect, useState } from "react";
import {
  ChevronDown,
  ChevronRight,
  Search,
  Settings,
  History,
  BookOpen,
  HelpCircle,
} from "lucide-react";
import { CiCircleInfo } from "react-icons/ci";
import { LuArrowLeftToLine, LuArrowRightToLine, LuLayoutDashboard } from "react-icons/lu";
import { cn } from "@/lib/utils";
import {
  ACTION_HEADERS,
  ActionHeaderType,
  type NodeCategory,
} from "@/lib/types/nodes/nodes";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Separator } from "@/components/ui/separator";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "../ui/dialog";
import { useRouter } from "next/navigation";
import { useWorkflowStore } from "@/lib/store/workflow";
import { searchNode } from "@/lib/api/workflow";
import { useIsMobile } from "@/hooks/use-mobile";

interface NodeSidebarProps {
  onNodeSelect: (nodeId: string) => void;
  onOpenDashboard: () => void;
}

export function NodeSidebar({ onNodeSelect, onOpenDashboard }: NodeSidebarProps) {
  const { nodeDefinitions } = useWorkflowStore();
  const [expandedCategories, setExpandedCategories] = useState<
    Set<string>
  >(new Set());
  const [searchQuery, setSearchQuery] = useState("");
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [dialogActiveCategory, setDialogActiveCategory] = useState<ActionHeaderType | null>(null);
  const [searchedNodes, setSearchedWorkflows] = useState<any[]>([]);
  const router = useRouter();
  const isMobile = useIsMobile();

  // We can use a simple custom mobile checker or the use-mobile hook
  useEffect(() => {
    if (typeof window !== 'undefined' && window.innerWidth < 768) {
      setSidebarCollapsed(true);
    }
  }, []);

  // Debounced search logic using the backend API
  useEffect(() => {
    if (!searchQuery.trim()) {
      setSearchedWorkflows([]);
      return;
    }

    const delayDebounceFn = setTimeout(async () => {
      try {
        const response = await searchNode({ q: searchQuery, category: '' });
        // Assume response.data.nodes or response.nodes contains the nodes
        const nodes = response?.data?.nodes || response?.nodes || (Array.isArray(response) ? response : []);
        setSearchedWorkflows(nodes);
      } catch (err) {
        console.error("Error searching nodes via API:", err);
      }
    }, 300);

    return () => clearTimeout(delayDebounceFn);
  }, [searchQuery]);

  const toggleCategory = (category: string) => {
    const newExpanded = new Set(expandedCategories);
    if (newExpanded.has(category)) {
      newExpanded.delete(category);
    } else {
      newExpanded.add(category);
    }
    setExpandedCategories(newExpanded);
  };

  const handleNodeClick = (nodeType: string) => {
    onNodeSelect(nodeType);
    // On mobile, automatically collapse the sidebar after selecting a node so it doesn't block the screen
    if (window.innerWidth < 768) {
      setSidebarCollapsed(true);
    }
  };

  // Determine which list of nodes to render
  const isSearching = searchQuery.trim().length > 0;

  // Group nodes by category
  const groupedNodes: Record<string, any[]> = {};
  const activeList = isSearching ? searchedNodes : nodeDefinitions;
  
  activeList.forEach((node) => {
    const cat = node.category || "General";
    if (!groupedNodes[cat]) {
      groupedNodes[cat] = [];
    }
    groupedNodes[cat].push(node);
  });

  const categories = isSearching 
    ? Object.keys(groupedNodes)
    : Array.from(new Set(nodeDefinitions.map((node) => node.category || "General")));

  const renderSidebarButton = (
    icon: React.ReactNode,
    label: string,
    onClick?: () => void
  ) => (
    <Button
      variant="ghost"
      size="sm"
      className="w-full justify-start"
      onClick={onClick}
    >
      {icon}
      {!sidebarCollapsed && <span className="ml-2">{label}</span>}
    </Button>
  );

  return (
    <div
      className={cn(
        "border-r bg-gray-50 dark:bg-background flex flex-col h-full transition-all duration-300",
        "max-md:absolute max-md:left-0 max-md:top-0 max-md:z-20 max-md:shadow-xl",
        sidebarCollapsed ? "w-16" : "w-64"
      )}
    >
      <div className="p-4 border-b flex items-center justify-between">
        {!sidebarCollapsed && (
          <div className="relative flex-1 mr-2">
            <Search className="absolute left-2 top-2.5 h-4 w-4 text-muted-foreground" />
            <Input
              placeholder="Search nodes..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="pl-8"
            />
          </div>
        )}
        <Button
          variant="ghost"
          size="icon"
          onClick={() => setSidebarCollapsed(!sidebarCollapsed)}
          className="shrink-0"
        >
          {
            sidebarCollapsed
              ? <LuArrowRightToLine className="h-4 w-4" />
              : <LuArrowLeftToLine className="h-4 w-4" />
          }
        </Button>
      </div>

      <ScrollArea className="flex-1">
        {!sidebarCollapsed ? (
          <div className="p-2">
            {categories.map((category, index) => {
              const label = category;
              return (
                <div key={index} className="mb-2">
                  <button
                    onClick={() => toggleCategory(category)}
                    className={cn(
                      "w-full px-2 py-2 flex items-center justify-between rounded-md",
                      "hover:bg-accent hover:text-accent-foreground",
                      "transition-colors text-sm"
                    )}
                  >
                    <span className="font-medium">{label}</span>
                    {expandedCategories.has(category) ? (
                      <ChevronDown className="h-4 w-4" />
                    ) : (
                      <ChevronRight className="h-4 w-4" />
                    )}
                  </button>
                  {expandedCategories.has(category) &&
                    groupedNodes[category]?.map((node) => 
                      (
                        <button
                          key={node.type}
                          onClick={() => onNodeSelect(node.type)}
                          className={cn(
                            "w-full px-4 py-2 text-sm flex items-center gap-2 rounded-md",
                            "hover:bg-accent hover:text-accent-foreground",
                            "transition-colors text-left"
                          )}
                        >
                          {node.display_name}
                        </button>
                      )
                    )}
                  {expandedCategories.has(category) &&
                    ACTION_HEADERS.map((actionHeader) => {
                      return (
                        actionHeader.category !== category ? null :
                          <Tooltip key={actionHeader.id}>
                            <TooltipTrigger asChild>
                              <button
                                key={actionHeader.id}
                                onClick={() => setDialogActiveCategory(actionHeader.id)}
                                className={cn(
                                  "w-full px-4 py-2 text-sm flex items-center justify-between gap-2 rounded-md",
                                  "hover:bg-accent hover:text-accent-foreground",
                                  "transition-colors text-left font-semibold"
                                )}
                              >
                                {actionHeader.id}
                                <CiCircleInfo size={15} />
                              </button>
                            </TooltipTrigger>
                            <TooltipContent className="ml-2">
                              Click here to select a node
                            </TooltipContent>
                          </Tooltip>
                      );
                    }
                    )}
                </div>
              );
            })}
          </div>
        ) : (
          <div className="py-2">
            {categories.map((category) => (
              <Tooltip key={category}>
                <TooltipTrigger asChild>
                  <Button
                    variant="ghost"
                    size="icon"
                    className="w-full h-10 rounded-none"
                    onClick={() => {
                      setSidebarCollapsed(false);
                      toggleCategory(category);
                    }}
                  >
                    <ChevronRight className="h-4 w-4" />
                  </Button>
                </TooltipTrigger>
                <TooltipContent side="right" className="ml-2">
                  {category}
                </TooltipContent>
              </Tooltip>
            ))}
          </div>
        )
        }
      </ScrollArea >

      <Separator />

      <div
        className={cn("p-4 space-y-2", sidebarCollapsed ? "items-center" : "")}
      >
        {!sidebarCollapsed ? (
          <>
            {renderSidebarButton(<LuLayoutDashboard className="h-4 w-4" />, "Dashboard", () => router.push('/workflow'))}
            {/* {renderSidebarButton(<History className="h-4 w-4" />, "History")} */}
            {/* {renderSidebarButton(
              <BookOpen className="h-4 w-4" />,
              "Documentation"
            )} */}
            {/* {renderSidebarButton(<Settings className="h-4 w-4" />, "Settings")} */}
            {/* <div className="flex items-center justify-between">
              {renderSidebarButton(<HelpCircle className="h-4 w-4" />, "Help")}
            </div> */}
          </>
        ) : (
          <div className="flex flex-col items-center gap-2">

            {/* <Tooltip>
              <TooltipTrigger asChild>
                <Button variant="ghost" size="icon">
                  <History className="h-4 w-4" />
                </Button>
              </TooltipTrigger>
              <TooltipContent side="right">History</TooltipContent>
            </Tooltip>
            <Tooltip>
              <TooltipTrigger asChild>
                <Button variant="ghost" size="icon">
                  <BookOpen className="h-4 w-4" />
                </Button>
              </TooltipTrigger>
              <TooltipContent side="right">Documentation</TooltipContent>
            </Tooltip>
            <Tooltip>
              <TooltipTrigger asChild>
                <Button variant="ghost" size="icon">
                  <Settings className="h-4 w-4" />
                </Button>
              </TooltipTrigger>
              <TooltipContent side="right">Settings</TooltipContent>
            </Tooltip>
            <Tooltip>
              <TooltipTrigger asChild>
                <Button variant="ghost" size="icon">
                  <HelpCircle className="h-4 w-4" />
                </Button>
              </TooltipTrigger>
              <TooltipContent side="right">Help</TooltipContent>
            </Tooltip> */}
            {/* <ThemeToggle /> */}
          </div>
        )}
      </div>
      <Dialog open={dialogActiveCategory !== null} onOpenChange={(open) => {
        if (!open) {
          setDialogActiveCategory(null);
        }
      }}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Select Node</DialogTitle>
          </DialogHeader>
          <div className="flex flex-col gap-5">
            {nodeDefinitions.map((node) => (
              <button
                key={node.type}
                onClick={() => {
                  onNodeSelect(node.type);
                  setDialogActiveCategory(null);
                }}
                className={cn(
                  "w-full px-4 py-2 rounded-md font-semibold",
                  "hover:bg-accent hover:text-accent-foreground",
                  "transition-colors text-left flex flex-col gap-0 text-base justify-start items-start"
                )}
              >
                {node.display_name}
                <p className="text-sm">{node.description}</p>
              </button>
            ))}
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
