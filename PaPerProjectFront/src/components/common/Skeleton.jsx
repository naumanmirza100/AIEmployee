/**
 * Reusable skeleton loading placeholders.
 * Usage: <Skeleton.ChatList />, <Skeleton.MeetingCard />, <Skeleton.Line />
 */

const shimmer = 'animate-pulse bg-white/[0.06] rounded';

function Line({ className = '', width = 'w-full' }) {
  return <div className={`h-3 ${shimmer} ${width} ${className}`} />;
}

function Circle({ size = 'h-10 w-10' }) {
  return <div className={`${shimmer} rounded-full ${size}`} />;
}

function ChatListItem() {
  return (
    <div className="p-3 space-y-2">
      <Line width="w-3/4" />
      <Line width="w-1/2" className="h-2" />
    </div>
  );
}

function ChatList({ count = 5 }) {
  return (
    <div className="space-y-2 p-2">
      {Array.from({ length: count }).map((_, i) => (
        <div key={i} className="rounded-lg border border-white/5 overflow-hidden">
          <ChatListItem />
        </div>
      ))}
    </div>
  );
}

function MeetingCard() {
  return (
    <div className="rounded-xl border border-white/10 bg-white/[0.02] p-4 space-y-3">
      <div className="flex items-start justify-between">
        <div className="space-y-2 flex-1">
          <Line width="w-48" className="h-4" />
          <Line width="w-32" className="h-2" />
        </div>
        <div className={`h-6 w-20 ${shimmer} rounded-full`} />
      </div>
      <div className="flex gap-4">
        <Line width="w-36" className="h-2" />
        <Line width="w-16" className="h-2" />
      </div>
    </div>
  );
}

function MeetingList({ count = 3 }) {
  return (
    <div className="space-y-4">
      {Array.from({ length: count }).map((_, i) => (
        <MeetingCard key={i} />
      ))}
    </div>
  );
}

function TaskCard() {
  return (
    <div className="rounded-xl border border-white/10 bg-white/[0.02] p-4 space-y-2">
      <Line width="w-56" className="h-4" />
      <Line width="w-full" className="h-2" />
      <div className="flex gap-2 pt-1">
        <div className={`h-5 w-16 ${shimmer} rounded-full`} />
        <div className={`h-5 w-20 ${shimmer} rounded-full`} />
        <div className={`h-5 w-24 ${shimmer} rounded-full`} />
      </div>
    </div>
  );
}

function TaskList({ count = 4 }) {
  return (
    <div className="space-y-3">
      {Array.from({ length: count }).map((_, i) => (
        <TaskCard key={i} />
      ))}
    </div>
  );
}

function StatsGrid({ count = 4 }) {
  return (
    <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
      {Array.from({ length: count }).map((_, i) => (
        <div key={i} className="rounded-xl border border-white/10 bg-white/[0.02] p-5 space-y-2">
          <Circle size="h-8 w-8" />
          <Line width="w-12" className="h-6" />
          <Line width="w-20" className="h-2" />
        </div>
      ))}
    </div>
  );
}

const Skeleton = {
  Line,
  Circle,
  ChatList,
  ChatListItem,
  MeetingCard,
  MeetingList,
  TaskCard,
  TaskList,
  StatsGrid,
};

export default Skeleton;
