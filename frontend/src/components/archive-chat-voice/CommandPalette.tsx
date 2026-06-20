import React, { useState, useCallback } from "react";
import { PiSparkleLight } from "react-icons/pi";
import { IoMailOutline } from "react-icons/io5";
import type { Command } from "@/types/chat";

interface CommandPaletteProps {
  onCommand?: (command: Command) => void;
  isOpen?: boolean;
  onClose?: () => void;
}

export const CommandPalette: React.FC<CommandPaletteProps> = ({
  onCommand,
  isOpen: propIsOpen,
  onClose,
}) => {
  const [isOpen, setIsOpen] = useState(false);
  const [search, setSearch] = useState("");

  const commands: Command[] = [
    {
      id: "imagen",
      name: "Generate Image",
      description: "Create AI-generated images",
      prefix: "/imagen",
      icon: <PiSparkleLight className="w-5 h-5" />,
    },
    {
      id: "email",
      name: "Write Email",
      description: "Generate professional emails",
      prefix: "/email",
      icon: <IoMailOutline className="w-5 h-5" />,
    },
    // Add more commands as needed
  ];

  const filteredCommands = commands.filter(
    (command) =>
      command.name.toLowerCase().includes(search.toLowerCase()) ||
      command.description.toLowerCase().includes(search.toLowerCase())
  );

  const handleCommandSelect = useCallback(
    (command: Command) => {
      onCommand?.(command);
      setIsOpen(false);
      onClose?.();
    },
    [onCommand, onClose]
  );

  const showPalette = propIsOpen ?? isOpen;

  if (!showPalette) return null;

  return (
    <div className="fixed inset-0 z-50 overflow-y-auto">
      <div className="min-h-[98vh] px-4 text-center">
        {/* Overlay */}
        <div
          className="fixed inset-0 bg-black/50 transition-opacity"
          onClick={() => {
            setIsOpen(false);
            onClose?.();
          }}
        />

        {/* Command Palette */}
        <div className="inline-block w-full max-w-md my-8 text-left align-middle transition-all transform bg-white shadow-xl rounded-xl">
          {/* Search Input */}
          <div className="p-4 border-b">
            <input
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search commands..."
              className="w-full px-4 py-2 text-sm border rounded-lg focus:outline-none focus:ring-2 focus:ring-orange-500"
              autoFocus
            />
          </div>

          {/* Commands List */}
          <div className="max-h-96 overflow-y-auto">
            {filteredCommands.length === 0 ? (
              <div className="p-4 text-sm text-gray-500 text-center">
                No commands found
              </div>
            ) : (
              <div className="py-2">
                {filteredCommands.map((command) => (
                  <button
                    key={command.id}
                    onClick={() => handleCommandSelect(command)}
                    className="w-full px-4 py-2 text-left hover:bg-gray-100 flex items-center gap-3"
                  >
                    <span className="text-orange-500">{command.icon}</span>
                    <div>
                      <div className="font-medium">{command.name}</div>
                      <div className="text-sm text-gray-500">
                        {command.description}
                      </div>
                    </div>
                  </button>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};
