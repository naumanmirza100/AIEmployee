import React from 'react';
import { Button } from '@/components/ui/button';
import { MessageCircle } from 'lucide-react';

const WhatsAppButton = () => {
  const phoneNumber = "447466436417";
  const message = "Need help submitting your project? Just say hi.";
  const whatsappUrl = `https://wa.me/${phoneNumber}?text=${encodeURIComponent(message)}`;

  return (
    <a href={whatsappUrl} target="_blank" rel="noopener noreferrer" className="block w-full mt-auto pt-4">
      <Button className="w-full font-bold bg-green-500 hover:bg-green-600 text-pure-white">
        <MessageCircle className="mr-2 h-5 w-5" />
        Chat on WhatsApp
      </Button>
    </a>
  );
};

export default WhatsAppButton;