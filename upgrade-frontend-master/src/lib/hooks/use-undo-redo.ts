// File: /lib/hooks/use-undo-redo.ts

import { useState, useCallback } from 'react';
import { Node, Edge } from '@xyflow/react';

interface HistoryItem {
  nodes: Node[];
  edges: Edge[];
}

interface UseUndoRedoProps {
  nodes: Node[];
  edges: Edge[];
  onNodesChange: (changes: unknown) => void;
  onEdgesChange: (changes: unknown) => void;
}

export function useUndoRedo({ nodes, edges, onNodesChange, onEdgesChange }: UseUndoRedoProps) {
  const [history, setHistory] = useState<HistoryItem[]>([]);
  const [currentIndex, setCurrentIndex] = useState<number>(-1);
  const [lastSavedState, setLastSavedState] = useState<string>('');

  // Deep clone nodes and edges to avoid reference issues
  const cloneState = (nodes: Node[], edges: Edge[]): HistoryItem => {
    return {
      nodes: JSON.parse(JSON.stringify(nodes)),
      edges: JSON.parse(JSON.stringify(edges)),
    };
  };

  const addHistoryItem = useCallback((state: HistoryItem) => {
    // Don't add if it's the same as the last state
    const stateString = JSON.stringify(state);
    if (stateString === lastSavedState) {
      return;
    }

    // If we're not at the end of the history, remove future states
    if (currentIndex < history.length - 1) {
      setHistory(history.slice(0, currentIndex + 1));
    }

    // Add the new state to history
    setHistory(prev => [...prev, cloneState(state.nodes, state.edges)]);
    setCurrentIndex(prev => prev + 1);
    setLastSavedState(stateString);
  }, [history, currentIndex, lastSavedState]);

  const undo = useCallback(() => {
    if (currentIndex <= 0) return;
    
    const prevState = history[currentIndex - 1];
    
    // Apply the previous state
    const nodesToRemove = nodes.filter(
      node => !prevState.nodes.find(n => n.id === node.id)
    ).map(node => ({ type: 'remove' as const, id: node.id }));
    
    const edgesToRemove = edges.filter(
      edge => !prevState.edges.find(e => e.id === edge.id)
    ).map(edge => ({ type: 'remove' as const, id: edge.id }));
    
    // First remove items that don't exist in previous state
    if (nodesToRemove.length > 0) onNodesChange(nodesToRemove);
    if (edgesToRemove.length > 0) onEdgesChange(edgesToRemove);
    
    // Then add or update items from previous state
    prevState.nodes.forEach(node => {
      const existingNode = nodes.find(n => n.id === node.id);
      if (!existingNode) {
        onNodesChange([{ type: 'add', item: node }]);
      } else {
        onNodesChange([{ 
          type: 'replace', 
          id: node.id, 
          item: node 
        }]);
      }
    });
    
    prevState.edges.forEach(edge => {
      const existingEdge = edges.find(e => e.id === edge.id);
      if (!existingEdge) {
        onEdgesChange([{ type: 'add', item: edge }]);
      } else {
        onEdgesChange([{ 
          type: 'replace', 
          id: edge.id, 
          item: edge 
        }]);
      }
    });
    
    setCurrentIndex(prev => prev - 1);
  }, [currentIndex, history, nodes, edges, onNodesChange, onEdgesChange]);

  const redo = useCallback(() => {
    if (currentIndex >= history.length - 1) return;
    
    const nextState = history[currentIndex + 1];
    
    // Apply the next state
    const nodesToRemove = nodes.filter(
      node => !nextState.nodes.find(n => n.id === node.id)
    ).map(node => ({ type: 'remove' as const, id: node.id }));
    
    const edgesToRemove = edges.filter(
      edge => !nextState.edges.find(e => e.id === edge.id)
    ).map(edge => ({ type: 'remove' as const, id: edge.id }));
    
    // First remove items that don't exist in next state
    if (nodesToRemove.length > 0) onNodesChange(nodesToRemove);
    if (edgesToRemove.length > 0) onEdgesChange(edgesToRemove);
    
    // Then add or update items from next state
    nextState.nodes.forEach(node => {
      const existingNode = nodes.find(n => n.id === node.id);
      if (!existingNode) {
        onNodesChange([{ type: 'add', item: node }]);
      } else {
        onNodesChange([{ 
          type: 'replace', 
          id: node.id, 
          item: node 
        }]);
      }
    });
    
    nextState.edges.forEach(edge => {
      const existingEdge = edges.find(e => e.id === edge.id);
      if (!existingEdge) {
        onEdgesChange([{ type: 'add', item: edge }]);
      } else {
        onEdgesChange([{ 
          type: 'replace', 
          id: edge.id, 
          item: edge 
        }]);
      }
    });
    
    setCurrentIndex(prev => prev + 1);
  }, [currentIndex, history, nodes, edges, onNodesChange, onEdgesChange]);

  return {
    undo,
    redo,
    canUndo: currentIndex > 0,
    canRedo: currentIndex < history.length - 1,
    addHistoryItem,
    history,
    currentIndex,
  };
}