import { createBrowserRouter, Navigate } from 'react-router-dom'

import { Shell } from '@/components/shell/Shell'
import { DuplicateReviewScreen } from '@/routes/DuplicateReviewScreen'
import { InboxScreen } from '@/routes/InboxScreen'
import { ReviewScreen } from '@/routes/ReviewScreen'

// Routes are named per ADR-0005 / Q5 — one screen per route. Search is the
// Cmd+K palette mounted from Shell, not a standalone route.
export const router = createBrowserRouter([
  {
    path: '/',
    element: <Shell />,
    children: [
      { index: true, element: <Navigate to="/inbox" replace /> },
      { path: 'inbox', element: <InboxScreen /> },
      { path: 'invoice/:id', element: <ReviewScreen /> },
      { path: 'duplicate-review/:id', element: <DuplicateReviewScreen /> },
    ],
  },
])
