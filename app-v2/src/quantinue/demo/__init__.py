"""Demo-only harness parts for the presentation video.

이 패키지는 촬영용 일회용 런타임(8022 + DB 5490)에서만 조립된다.
운영 기본 경로(main.create_app 기본 조립, watch/job factory)는 이 패키지를
import하면 안 된다 — 데모 부품이 운영에 새어 들어가는 것을 막는 금지선이다
(demo-video-plan.md §5).
"""
