import { createBrowserRouter, Navigate } from 'react-router-dom'

import { Shell } from '@/components/shell/Shell'
import { AnomaliesScreen } from '@/routes/AnomaliesScreen'
import { DuplicateReviewScreen } from '@/routes/DuplicateReviewScreen'
import { InboxScreen } from '@/routes/InboxScreen'
import { LoginScreen } from '@/routes/LoginScreen'
import { ReviewScreen } from '@/routes/ReviewScreen'
import { SearchScreen } from '@/routes/SearchScreen'
import { VendorsScreen } from '@/routes/VendorsScreen'

export const router = createBrowserRouter([
  { path: '/login', element: <LoginScreen /> },
  {
    path: '/',
    element: <Shell />,
    children: [
      { index: true, element: <Navigate to="/inbox" replace /> },
      { path: 'inbox', element: <InboxScreen /> },
      { path: 'anomalies', element: <AnomaliesScreen /> },
      { path: 'invoice/:id', element: <ReviewScreen /> },
      { path: 'duplicate-review/:id', element: <DuplicateReviewScreen /> },
      { path: 'search', element: <SearchScreen /> },
      { path: 'vendors', element: <VendorsScreen /> },
    ],
  },
])
