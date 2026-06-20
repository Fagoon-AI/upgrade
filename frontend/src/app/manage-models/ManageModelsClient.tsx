"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Button } from "@/components/ui/button";
import { useUserStore } from "@/lib/store/user";
import { getModels } from "@/lib/api/models";
import { ModelResponse } from "@/lib/schemas/model";
import { ModelList } from "@/components/manage-models/ModelList";
import { AddModelModal } from "@/components/manage-models/AddModelModal";
import { Loader } from "@/components/ui/loader";
import { Plus } from "lucide-react";

export function ManageModelsClient() {
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [editingModelId, setEditingModelId] = useState<string | null>(null);

  // TanStack Query to Fetch Models
  const { data: models = [], isLoading: fetchingData } = useQuery<ModelResponse[]>({
    queryKey: ["models"],
    queryFn: async () => {
      const response = await getModels();
      return response.data || response || [];
    },
  });

  if (fetchingData) {
    return (
      <div className="flex items-center justify-center h-full min-h-[50vh]">
        <Loader size="md" text="Loading models inventory..." />
      </div>
    );
  }

  return (
    <div className="container mx-auto py-10 max-w-3xl text-slate-800 dark:text-gray-200">
      <div className="flex items-center justify-between mb-8">
        <h1 className="text-3xl font-bold text-slate-900 dark:text-gray-100">Manage Models</h1>
        <Button
          onClick={() => {
            setEditingModelId(null);
            setIsModalOpen(true);
          }}
          className="bg-slate-900 text-white hover:bg-slate-800 dark:bg-white dark:text-black dark:hover:bg-gray-200"
        >
          <Plus className="w-4 h-4 mr-2" />
          Add New Model
        </Button>
      </div>

      {/* Main List Component */}
      <ModelList
        models={models}
        onAddNewModel={() => {
          setEditingModelId(null);
          setIsModalOpen(true);
        }}
        onEditModel={(id) => {
          setEditingModelId(id);
          setIsModalOpen(true);
        }}
      />

      {/* Form logic inside Modal Dialog */}
      <AddModelModal
        isOpen={isModalOpen}
        onClose={() => {
          setIsModalOpen(false);
          setEditingModelId(null);
        }}
        editingModelId={editingModelId}
      />
    </div>
  );
}
