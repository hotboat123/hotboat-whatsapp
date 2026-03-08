#!/usr/bin/env python3
"""
Test script for priority system
"""
import asyncio
import os
from app.db.leads import get_or_create_lead, update_lead_priority

async def test_priority_system():
    """Test the priority system"""
    print("🧪 Testing Priority System\n")
    
    # Test phone number
    test_phone = "56999999999"
    
    # 1. Create/get a test lead
    print(f"1️⃣ Creating/getting test lead for {test_phone}...")
    lead = await get_or_create_lead(test_phone, "Test User")
    
    if lead:
        print(f"✅ Lead created/retrieved: {lead['customer_name']}")
        print(f"   Current priority: {lead.get('priority', 0)}")
    else:
        print("❌ Failed to create/get lead")
        return
    
    # 2. Test setting different priorities
    priorities = [1, 2, 3, 0]
    priority_names = {
        0: "Sin prioridad",
        1: "Alta (Rojo)",
        2: "Media (Naranja)",
        3: "Baja (Amarillo)"
    }
    
    for priority in priorities:
        print(f"\n2️⃣ Setting priority to {priority} ({priority_names[priority]})...")
        success = await update_lead_priority(test_phone, priority)
        
        if success:
            print(f"✅ Priority updated to {priority}")
            
            # Verify the update
            lead = await get_or_create_lead(test_phone)
            current_priority = lead.get('priority', 0)
            
            if current_priority == priority:
                print(f"✅ Verified: Priority is {current_priority}")
            else:
                print(f"❌ Error: Expected {priority}, got {current_priority}")
        else:
            print(f"❌ Failed to update priority to {priority}")
    
    # 3. Test invalid priority
    print(f"\n3️⃣ Testing invalid priority (4)...")
    success = await update_lead_priority(test_phone, 4)
    
    if not success:
        print("✅ Correctly rejected invalid priority")
    else:
        print("❌ Should have rejected invalid priority")
    
    print("\n✨ Test completed!")

if __name__ == "__main__":
    # Check DATABASE_URL
    if not os.getenv('DATABASE_URL'):
        print("❌ ERROR: DATABASE_URL not set")
        print("Please set it in your .env file or environment")
        exit(1)
    
    asyncio.run(test_priority_system())
