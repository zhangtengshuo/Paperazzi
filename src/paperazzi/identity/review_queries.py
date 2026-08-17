"""Read-only identity review list query with human-readable author subjects."""
from __future__ import annotations
from typing import Any
import sqlalchemy as sa
from paperazzi.database.models import PaperCreatorMention
from .models import Author, ResolutionReviewQueue


def list_identity_review_queue(session:Any,*,limit:int=100)->list[dict[str,Any]]:
    """Return ranked identity reviews in one bounded SELECT.

    Creator-mention subjects show the exact source spelling; canonical-author subjects
    (e.g. SIMILAR_NAME_VARIANTS) show the preferred canonical name instead of a ULID.
    """
    capped=min(max(1,limit),500)
    first_orders=(sa.select(PaperCreatorMention.paper_id.label('paper_id'),sa.func.min(PaperCreatorMention.order_index).label('first_order')).where(PaperCreatorMention.creator_type=='author').group_by(PaperCreatorMention.paper_id).subquery())
    mention=sa.orm.aliased(PaperCreatorMention);author=sa.orm.aliased(Author)
    creator_subject=sa.and_(ResolutionReviewQueue.subject_type=='creator_mention',sa.cast(ResolutionReviewQueue.subject_id,sa.Integer)==mention.creator_mention_id)
    author_subject=sa.and_(ResolutionReviewQueue.subject_type=='author',ResolutionReviewQueue.subject_id==author.author_id)
    role_priority=sa.case(
        (ResolutionReviewQueue.queue_type=='UNRESOLVED_CORRESPONDING_AUTHOR',100),
        (sa.and_(mention.creator_mention_id.is_not(None),mention.order_index==first_orders.c.first_order),90),
        else_=0,
    )
    effective=sa.func.max(ResolutionReviewQueue.priority,role_priority)
    rows=(session.query(
        ResolutionReviewQueue.review_item_id,ResolutionReviewQueue.queue_type,
        ResolutionReviewQueue.subject_type,ResolutionReviewQueue.subject_id,
        ResolutionReviewQueue.candidate_id,ResolutionReviewQueue.reason_code,
        ResolutionReviewQueue.priority,effective.label('effective_priority'),
        mention.display_name,mention.first_name,mention.last_name,mention.paper_id,
        author.preferred_name.label('canonical_name'),
    ).outerjoin(mention,creator_subject).outerjoin(first_orders,first_orders.c.paper_id==mention.paper_id).outerjoin(author,author_subject)
      .filter(ResolutionReviewQueue.status=='OPEN',ResolutionReviewQueue.queue_type.in_(['AMBIGUOUS_AUTHOR_IDENTITY','IDENTITY_CONFLICT','SIMILAR_AUTHOR_IDENTITY','UNRESOLVED_CORRESPONDING_AUTHOR']))
      .order_by(effective.desc(),ResolutionReviewQueue.review_item_id).limit(capped).all())
    out=[]
    for r in rows:
        if r.subject_type=='creator_mention':
            name=r.display_name or ' '.join(x for x in (r.first_name,r.last_name) if x) or 'Unknown author'
        elif r.subject_type=='author':
            name=r.canonical_name or r.subject_id
        else:name=None
        out.append({'review_item_id':r.review_item_id,'queue_type':r.queue_type,'subject_type':r.subject_type,'subject_id':r.subject_id,'candidate_id':r.candidate_id,'reason_code':r.reason_code,'stored_priority':r.priority,'effective_priority':int(r.effective_priority),'source_name':name,'paper_id':r.paper_id})
    return out
