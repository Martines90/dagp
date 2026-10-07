#!/usr/bin/env python3
"""Run deterministic nested-governance and identity-merger reference stories.
Uses the small adversarial test fixture (reduced board probability target), not
production cryptography, remote finality proofs or a performance benchmark.
"""
import argparse
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'chain/reference'))
from dagp_ref.roles import Status
from tests.test_societies import NestedSocieties,Mergers


def state(tree):
    tree.treasury.assert_invariants()
    if not tree.reg.verify_audit():raise AssertionError('invalid identity/governance audit chain')
    return dict(chain=tree.chain,jurisdictions=sorted(tree.nodes),
                active_citizens=sum(i.status is Status.ACTIVE for i in tree.reg.ids.values()),
                treasury_free=tree.treasury.free,reserved=sum(tree.treasury.reserved.values()),
                escrow=sum(tree.treasury.escrow.values()),audit_events=len(tree.reg.audit),
                audit_head=tree.reg.audit[-1]['hash'])


def run():
    stories=[]
    cases=[(NestedSocieties,'test_dual_consensus_creates_child_and_grandchild'),
           (NestedSocieties,'test_real_local_review_vote_final_parent_checks_and_milestone_escrow'),
           (NestedSocieties,'test_partial_local_bill_reserves_whole_ceiling_and_only_funds_approved_points'),
           (Mergers,'test_bilateral_vote_optin_preserves_history_without_offices'),
           (Mergers,'test_existing_members_deduplicate_and_keep_only_receiving_authority')]
    for cls,name in cases:
        case=cls(name);case.setUp()
        try:
            getattr(case,name)()
            if cls is NestedSocieties:story=dict(story=name,state=state(case.w.tree))
            else:story=dict(story=name,source=state(case.a.tree),destination=state(case.b.tree),
                            merger_state=case.merge.state,claims=dict(case.merge._claimed))
            stories.append(story)
        finally:case.tearDown()
    return stories


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=Path('/private/tmp/dagp-institutions-report.json'))
    args=parser.parse_args()
    first,second=run(),run()
    if first!=second:raise AssertionError('independent deterministic replay differs')
    report=dict(schema_version=1,implementation='Python reference, small synthetic fixtures',
                production_claim=False,replay_equal=True,stories=first,
                limits=['HMAC simulation keys','trusted keeper/identity/beacon/payment inputs',
                        'reduced small-fixture board probability target',
                        'no remote consensus proofs, asset bridge or production throughput claim'])
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,indent=2)+'\n')
    print(f'{len(first)} institutional stories passed; independent replay identical; report: {args.output}')

if __name__=='__main__':main()
