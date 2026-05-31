import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

export default function MarkdownRenderer({ content }) {
  return (
    <div className="prose prose-invert max-w-none 
                    prose-p:text-sm prose-p:leading-relaxed 
                    prose-headings:font-bold prose-headings:text-brand-light 
                    prose-h2:text-lg prose-h2:mt-4 prose-h2:mb-2
                    prose-h3:text-base prose-h3:mt-3 prose-h3:mb-1
                    prose-strong:text-white prose-strong:font-semibold
                    prose-ul:my-2 prose-ul:list-disc prose-ul:pl-5
                    prose-ol:my-2 prose-ol:list-decimal prose-ol:pl-5
                    prose-li:my-1
                    prose-table:w-full prose-table:text-sm prose-table:my-4 prose-table:border-collapse
                    prose-th:border prose-th:border-brand-primary/30 prose-th:bg-brand-primary/20 prose-th:px-3 prose-th:py-2 prose-th:text-left
                    prose-td:border prose-td:border-brand-primary/30 prose-td:px-3 prose-td:py-2
                    prose-hr:border-brand-primary/30 prose-hr:my-4">
      <ReactMarkdown remarkPlugins={[remarkGfm]}>
        {content}
      </ReactMarkdown>
    </div>
  );
}
