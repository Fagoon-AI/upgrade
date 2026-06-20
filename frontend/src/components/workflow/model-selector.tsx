"use client";

import { useState } from 'react';
import { Check, ChevronDown } from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
} from '@/components/ui/command';
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from '@/components/ui/popover';
import { AIModel, AIModelType, AI_MODELS } from '@/lib/types/workflow';

interface ModelSelectorProps {
  nodeType: AIModelType;
  selectedModelId?: string;
  onSelect: (model: AIModel) => void;
}

export function ModelSelector({ nodeType, selectedModelId, onSelect }: ModelSelectorProps) {
  const [open, setOpen] = useState(false);
  const filteredModels = AI_MODELS.filter(model => model.type === nodeType);
  const selectedModel = AI_MODELS.find(model => model.id === selectedModelId);

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button
          variant="outline"
          role="combobox"
          aria-expanded={open}
          className="w-full justify-between"
        >
          {selectedModel ? selectedModel.name : "Select model..."}
          <ChevronDown className="ml-2 h-4 w-4 shrink-0 opacity-50" />
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-[300px] p-0">
        <Command>
          <CommandInput placeholder="Search models..." />
          <CommandEmpty>No model found.</CommandEmpty>
          <CommandGroup>
            {filteredModels.map((model) => (
              <CommandItem
                key={model.id}
                value={model.id}
                onSelect={() => {
                  onSelect(model);
                  setOpen(false);
                }}
              >
                <Check
                  className={`mr-2 h-4 w-4 ${
                    selectedModelId === model.id ? "opacity-100" : "opacity-0"
                  }`}
                />
                <div className="flex flex-col">
                  <span>{model.name}</span>
                  <span className="text-xs text-muted-foreground">
                    {model.description}
                  </span>
                </div>
              </CommandItem>
            ))}
          </CommandGroup>
        </Command>
      </PopoverContent>
    </Popover>
  );
}