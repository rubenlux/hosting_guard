import SparklineChart from './SparklineChart';
import TopPagesMini   from './TopPagesMini';

/**
 * Groups sparkline and top pages into a single traffic block.
 *
 * Props:
 *   sparkline — number[] (page_views per day, 7 days)
 *   topPages  — { path, views, url }[] (max 3)
 */
export default function TrafficSection({ sparkline, topPages }) {
  return (
    <div className="space-y-3">
      <SparklineChart data={sparkline} />
      <TopPagesMini pages={topPages} />
    </div>
  );
}
