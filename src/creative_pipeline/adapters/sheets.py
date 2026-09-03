import csv
import io
from typing import Dict, List, Tuple

from creative_pipeline.models.schemas import (
    AssetType,
    BatchAssetDropped,
    BatchAssetInput,
    BatchAssetReady,
    BatchPipelineRequest,
)


class SheetsAdapter:
    """Helper adapter to parse CSV/Sheet rows and export processed assets."""

    @staticmethod
    def parse_csv_to_requests(csv_text: str) -> List[BatchPipelineRequest]:
        """Parses CSV text formatted with columns:

        ad_group_alias, asset_type, content, orientation (optional)
        Groups rows by ad_group_alias.
        """
        reader = csv.DictReader(io.StringIO(csv_text.strip()))
        groups: Dict[str, List[BatchAssetInput]] = {}

        for row in reader:
            # Case-insensitive column resolution
            normalized = {k.strip().lower(): v.strip() for k, v in row.items() if k}
            alias = normalized.get("ad_group_alias") or normalized.get("campaign") or "Default_Group"
            type_str = (normalized.get("asset_type") or normalized.get("type") or "").upper()
            content = normalized.get("content") or normalized.get("text") or normalized.get("url") or ""
            orientation = normalized.get("orientation")

            if not content or type_str not in AssetType.__members__:
                continue

            asset_input = BatchAssetInput(
                type=AssetType[type_str],
                content=content,
                orientation=orientation,
            )

            if alias not in groups:
                groups[alias] = []
            groups[alias].append(asset_input)

        requests = [
            BatchPipelineRequest(ad_group_alias=alias, assets=assets)
            for alias, assets in groups.items()
        ]
        return requests

    @staticmethod
    def export_to_csv(
        ad_group_alias: str,
        ready_assets: List[BatchAssetReady],
        dropped_assets: List[BatchAssetDropped],
    ) -> str:
        """Exports processed ready assets and dropped report into CSV string."""
        output = io.StringIO()
        writer = csv.writer(output)

        # Header for production ready assets
        writer.writerow(["=== READY ASSETS (PRODUCTION UPLOAD) ==="])
        writer.writerow(["ad_group_alias", "asset_type", "orientation", "content", "metadata"])
        for asset in ready_assets:
            writer.writerow([
                ad_group_alias,
                asset.type.value,
                asset.orientation or "",
                asset.content,
                str(asset.metadata or ""),
            ])

        writer.writerow([])
        # Header for dropped assets report
        writer.writerow(["=== DROPPED ASSETS (REMEDIATION NEEDED) ==="])
        writer.writerow(["ad_group_alias", "asset_type", "original_content", "drop_reason"])
        for dropped in dropped_assets:
            writer.writerow([
                ad_group_alias,
                dropped.type.value,
                dropped.content,
                dropped.reason,
            ])

        return output.getvalue()
