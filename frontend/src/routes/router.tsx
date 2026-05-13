import { createBrowserRouter, Navigate } from 'react-router-dom'

import { Shell } from '@/components/shell/Shell'
import { InboxScreen } from '@/routes/InboxScreen'
import { ReviewScreen } from '@/routes/ReviewScreen'
import { DuplicateReviewScreen } from '@/routes/DuplicateReviewScreen'
import { SearchScreen } from '@/routes/SearchScreen'

// Routes are named per ADR-0005 / Q5 — one screen per route, no mode toggles.
export const router = createBrowserRouter([
  {
    path: '/',
    element: <Shell />,
    children: [
      { index: true, element: <Navigate to="/inbox" replace /> },
      { path: 'inbox', element: <InboxScreen /> },
      { path: 'invoice/:id', element: <ReviewScreen /> },
      { path: 'duplicate-review/:id', element: <DuplicateReviewScreen /> },
      { path: 'search', element: <SearchScreen /> },
    ],
  },
])
