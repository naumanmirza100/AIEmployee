/**
 * HROrgChartTab — collapsible tree view of departments + their employees.
 * Backend: GET /hr/org-chart. Renders the recursive department tree shape:
 *   { id, name, type: 'department', head, employees, children }
 *
 * Click an employee chip to open the HREmployeeDetailDrawer.
 */
import React, { useEffect, useState } from 'react';
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { useToast } from '@/components/ui/use-toast';
import {
  Loader2, Network, RefreshCw, ChevronDown, ChevronRight, Crown,
} from 'lucide-react';
import hrAgentService from '@/services/hrAgentService';


function DepartmentNode({ node, level, onOpenEmployee }) {
  const [open, setOpen] = useState(level < 1);
  const hasContent = (node.children?.length || 0) + (node.employees?.length || 0) > 0;
  const indent = level * 14;

  return (
    <div>
      <div className="flex items-center gap-1.5 py-1.5"
        style={{ paddingLeft: indent }}>
        <button onClick={() => setOpen(!open)}
          className="text-white/50 hover:text-white/80 disabled:opacity-30"
          disabled={!hasContent}>
          {open ? <ChevronDown className="h-3.5 w-3.5" /> : <ChevronRight className="h-3.5 w-3.5" />}
        </button>
        <span className="font-semibold text-white/90 text-sm">{node.name}</span>
        {node.head && (
          <Badge variant="outline" className="text-[10px] bg-amber-500/10 text-amber-300 border-amber-400/30">
            <Crown className="h-2.5 w-2.5 mr-1" /> {node.head.full_name}
          </Badge>
        )}
        <span className="text-[10px] text-white/40 ml-1">
          {node.employees?.length || 0} · {node.children?.length || 0} subdept{(node.children?.length || 0) === 1 ? '' : 's'}
        </span>
      </div>

      {open && (
        <div>
          {node.employees && node.employees.length > 0 && (
            <div className="flex flex-wrap gap-1.5 mb-1.5"
              style={{ paddingLeft: indent + 24 }}>
              {node.employees.map((e) => (
                <button key={e.id}
                  onClick={() => onOpenEmployee && onOpenEmployee(e.id)}
                  className="text-[11px] px-2 py-1 rounded-md border border-white/[0.08] bg-white/[0.03] text-white/80 hover:bg-violet-500/10 hover:border-violet-400/30 hover:text-violet-200 transition-colors">
                  {e.full_name}
                  {e.job_title && <span className="text-white/45"> · {e.job_title}</span>}
                </button>
              ))}
            </div>
          )}
          {node.children && node.children.map((child) => (
            <DepartmentNode key={child.id || `unassigned-${child.name}`}
              node={child} level={level + 1} onOpenEmployee={onOpenEmployee} />
          ))}
        </div>
      )}
    </div>
  );
}


export default function HROrgChartTab({ onOpenEmployee }) {
  const { toast } = useToast();
  const [tree, setTree] = useState([]);
  const [loading, setLoading] = useState(false);

  const load = async () => {
    setLoading(true);
    try {
      const res = await hrAgentService.getHROrgChart();
      setTree(res?.data || []);
    } catch (e) {
      toast({ title: 'Failed to load org chart', description: e.message, variant: 'destructive' });
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, []);

  return (
    <Card className="border-white/10 bg-black/20 backdrop-blur-sm">
      <CardHeader className="flex flex-row items-center justify-between gap-3">
        <div>
          <CardTitle className="flex items-center gap-2">
            <Network className="h-5 w-5 text-violet-400" /> Org chart
          </CardTitle>
          <CardDescription>
            Departments + their head + employee leaves. Click any employee chip to open their drawer.
          </CardDescription>
        </div>
        <Button variant="outline" onClick={load} disabled={loading}>
          {loading ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <RefreshCw className="h-3.5 w-3.5" />}
          <span className="ml-1">Refresh</span>
        </Button>
      </CardHeader>
      <CardContent>
        {loading ? (
          <div className="flex justify-center py-8"><Loader2 className="h-5 w-5 animate-spin text-white/40" /></div>
        ) : tree.length === 0 ? (
          <div className="text-center py-10 text-white/50 text-sm">
            No departments yet. Create one in the Employees tab.
          </div>
        ) : (
          <div className="rounded-xl border border-white/[0.08] bg-white/[0.02] p-3 overflow-x-auto">
            {tree.map((root) => (
              <DepartmentNode key={root.id || `unassigned-${root.name}`}
                node={root} level={0} onOpenEmployee={onOpenEmployee} />
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
