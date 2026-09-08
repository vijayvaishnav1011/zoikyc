"""
Flask CLI commands for wallet management.
Run via:  flask wallet reconcile-pending
"""
import click
from flask import current_app
from app.wallet import wallet_bp


@wallet_bp.cli.command("reconcile-pending")
@click.option('--dry-run', is_flag=True, default=False, help="Print what would be done without committing.")
def reconcile_pending_cmd(dry_run):
    """
    Reconcile all pending Razorpay orders and credit wallets for captured payments.
    Meant to be run as a cron job or manually for recovery.

    Example cron (every 15 minutes):
        */15 * * * * cd /app && flask wallet reconcile-pending >> /var/log/wallet_reconcile.log 2>&1
    """
    from app.wallet.reconciliation import reconcile_pending_recharges

    if dry_run:
        click.echo("[DRY RUN] Would reconcile pending recharges (no changes committed).")
        return

    click.echo("🔄 Starting wallet reconciliation against Razorpay...")
    credited, failed, skipped = reconcile_pending_recharges()
    click.echo(
        f"✅ Reconciliation complete.\n"
        f"   💰 Wallets Credited : {credited}\n"
        f"   ❌ Failed Payments  : {failed}\n"
        f"   ⏭  Skipped / Active : {skipped}"
    )
