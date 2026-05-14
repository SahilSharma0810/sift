import { createBrowserRouter, Navigate } from 'react-router-dom'

import { Shell } from '@/components/shell/Shell'
import { DuplicateReviewScreen } from '@/routes/DuplicateReviewScreen'
import { InboxScreen } from '@/routes/InboxScreen'
import { ReviewScreen } from '@/routes/ReviewScreen'
import { SearchScreen } from '@/routes/SearchScreen'

// One screen per route. The Cmd+K palette is a fast-path for the same
// /api/search/translate endpoint the search page uses — both share the
// backend translator so behaviour matches everywhere.
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
