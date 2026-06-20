export interface CodeProps {
  node?: {
    type: string;
    tagName: string;
    properties: Record<string, unknown>;
    children: Array<{
      type: string;
      value: string;
    }>;
  };
  inline?: boolean;
  className?: string;
  children: string | React.ReactNode;
}

export interface MarkdownProps {
  children: React.ReactNode;
}

export interface DOMNode {
  type: string;
  name?: string;
  attribs?: {
    class?: string;
    [key: string]: string | undefined;
  };
  children?: DOMNode[];
  data?: string;
}
