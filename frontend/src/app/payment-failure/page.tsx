// 'use client'

// import React, { useEffect } from 'react';
// import { motion } from 'framer-motion';
// import { useRouter } from 'next/navigation';
// import { Card, CardContent } from '@/components/ui/card';
// import { FaRegTimesCircle } from 'react-icons/fa';

// const PaymentReject = () => {
//   const router = useRouter();
//   const [count, setCount] = React.useState(5);

//   // useEffect(() => {
//   //   const timer = setInterval(() => {
//   //     setCount((prev) => {
//   //       if (prev <= 1) {
//   //         clearInterval(timer);
//   //         router.push('/');
//   //         return 0;
//   //       }
//   //       return prev - 1;
//   //     });
//   //   }, 1000);

//   //   return () => clearInterval(timer);
//   // }, [router]);

//   return (
//     <div className="min-h-screen flex items-center justify-center p-4">
//       <Card className="w-full max-w-md bg-transparent">
//         <CardContent className="pt-6">
//           <motion.div
//             initial={{ scale: 0 }}
//             animate={{ scale: 1 }}
//             transition={{ 
//               type: "spring",
//               stiffness: 260,
//               damping: 20 
//             }}
//             className="flex justify-center"
//           >
//             <FaRegTimesCircle className="w-16 h-16 text-red-500" />
//           </motion.div>
          
//           <motion.div
//             initial={{ opacity: 0, y: 50 }}
//             animate={{ opacity: 1, y: 0 }}
//             transition={{ delay: 0.2 }}
//             className="text-center mt-6"
//           >
//             <h1 className="text-2xl font-bold ">
//               An Error has occured
//             </h1>
//             <p className="mt-2 text-gray-600">
//               Try again in a while
//             </p>
            
//             <motion.div
//               initial={{ opacity: 0 }}
//               animate={{ opacity: 1 }}
//               transition={{ delay: 0.4 }}
//               className="mt-6 text-sm text-gray-500"
//             >
//               Redirecting in {count} seconds...
//             </motion.div>
//           </motion.div>
//         </CardContent>
//       </Card>
//     </div>
//   );
// };

// export default PaymentReject;
'use client'

import { useRouter } from 'next/navigation'
import React, { useEffect } from 'react'
import { showErrorToast } from "@/utils/toast"

const PaymentFailure = () => {
    const router = useRouter()
    useEffect(()=>{
        showErrorToast('Payment has been failed')
        setTimeout(()=>{
            router.push('/')
        },100)
    },[])
  return (
    <div></div>
  )
}

export default PaymentFailure